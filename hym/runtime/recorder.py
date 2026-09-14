from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

from hym.adapters.airtest_poco import AirtestPocoDeviceFactory
from hym.adapters.local import LocalArtifactStore, SystemClock
from hym.core.config import RuntimeSettings
from hym.core.events import ConsoleEventSink, EventFilter, EventLevel, to_jsonable
from hym.core.models import ObservationRequest, UiNode, UiTreeSource, utc_now
from hym.core.ports import OcrEnginePort
from hym.locators.vision import create_ocr_engine
from hym.runtime.diagnostics import DiagnosticsService
from hym.runtime.lease import DeviceBusyError, DeviceLease
from hym.runtime.session import DeviceSession


class ManualFlowRecorder:
    """按人工确认点保存页面变化，用于把真机新流程转成代码。"""

    def __init__(
        self,
        *,
        session: DeviceSession,
        diagnostics: DiagnosticsService,
        manifest_path: Path,
        flow_name: str,
        app_label: str | None = None,
        ocr_engine: OcrEnginePort | None = None,
        input_fn: Callable[[str], str] = input,
        output_fn: Callable[[str], None] = print,
    ) -> None:
        self.session = session
        self.diagnostics = diagnostics
        self.manifest_path = manifest_path
        self.flow_name = flow_name.strip()
        if not self.flow_name:
            raise ValueError("流程名称不能为空")
        self.app_label = app_label.strip() if app_label else None
        self.ocr_engine = ocr_engine
        self.input_fn = input_fn
        self.output_fn = output_fn

    def run(self) -> int:
        started_at = utc_now()
        manifest: dict[str, Any] = {
            "schema_version": "1.0",
            "recording_id": uuid4().hex,
            "flow_name": self.flow_name,
            "app_label": self.app_label,
            "device_id": self.session.descriptor.device_id,
            "started_at": started_at.isoformat(),
            "status": "recording",
            "initial_capture": None,
            "steps": [],
        }
        initial = self._capture(0, "初始页面", None)
        manifest["initial_capture"] = initial
        self._save_manifest(manifest)
        if initial["status"] != "success":
            manifest["status"] = "failed"
            manifest["finished_at"] = utc_now().isoformat()
            self._save_manifest(manifest)
            self.output_fn("初始页面采集失败，记录已保留。")
            return 2

        self.output_fn("初始页面已保存。请在手机完成一步操作，再输入操作说明并回车。")
        self.output_fn("输入 :done 完成，:cancel 取消；直接回车会保存一个未说明操作的检查点。")
        previous = initial
        try:
            while True:
                note = self.input_fn("操作说明> ").strip()
                if note == ":done":
                    manifest["status"] = "completed"
                    break
                if note == ":cancel":
                    manifest["status"] = "cancelled"
                    break

                action_note = note or "未说明操作"
                index = len(manifest["steps"]) + 1
                current = self._capture(index, f"步骤{index}", action_note)
                transition = _transition(previous, current)
                manifest["steps"].append(
                    {
                        "index": index,
                        "action_note": action_note,
                        "before_capture_id": previous["capture_id"],
                        "after_capture": current,
                        "transition": transition,
                    }
                )
                self._save_manifest(manifest)
                previous = current
                change_text = "页面有变化" if transition["changed"] else "未发现稳定页面变化"
                self.output_fn(f"步骤 {index} 已保存，{change_text}。")
        except (EOFError, KeyboardInterrupt):
            manifest["status"] = "interrupted"

        manifest["finished_at"] = utc_now().isoformat()
        self._save_manifest(manifest)
        self.output_fn(f"流程记录已保存: {self.manifest_path}")
        return 0 if manifest["status"] == "completed" else 1

    def _capture(self, index: int, label: str, action_note: str | None) -> dict[str, Any]:
        result = self.session.observe(
            ObservationRequest(
                include_ui_tree=True,
                include_screenshot=True,
                ui_tree_source=UiTreeSource.AUTO,
            )
        )
        capture_id = uuid4().hex
        if not result.succeeded or result.observation is None:
            return {
                "capture_id": capture_id,
                "index": index,
                "label": label,
                "status": "failed",
                "message": result.message,
            }

        observation = result.observation
        capture_warnings = list(observation.metadata.get("warnings", ()))
        if not observation.ui_nodes:
            fallback = self.session.observe(
                ObservationRequest(
                    include_ui_tree=True,
                    include_screenshot=False,
                    ui_tree_source=UiTreeSource.ACCESSIBILITY,
                )
            )
            if fallback.succeeded and fallback.observation is not None:
                if fallback.observation.ui_nodes:
                    observation = replace(
                        observation,
                        ui_nodes=fallback.observation.ui_nodes,
                    )
                    capture_warnings.append("Poco UI 树为空，已使用原生无障碍树")
                else:
                    capture_warnings.append("Poco 和原生无障碍 UI 树均为空")
            elif fallback.message:
                capture_warnings.append(f"原生无障碍树获取失败: {fallback.message}")
        if self.ocr_engine is not None and observation.screenshot is not None:
            try:
                observation = replace(
                    observation,
                    ocr_texts=self.ocr_engine.recognize(observation.screenshot),
                )
            except Exception as error:
                capture_warnings.append(f"OCR 识别失败: {error}")
        refs = self.diagnostics.capture(
            f"{index:03d}-{label}",
            observation,
            metadata={
                "schema_version": "1.0",
                "purpose": "手动流程记录",
                "flow_name": self.flow_name,
                "step_index": index,
                "action_note": action_note,
            },
        )
        return {
            "capture_id": capture_id,
            "index": index,
            "label": label,
            "status": "success",
            "captured_at": observation.captured_at.isoformat(),
            "activity": {
                "package_name": observation.activity.package_name,
                "activity_name": observation.activity.activity_name,
            },
            "node_count": len(observation.ui_nodes),
            "markers": _stable_markers(observation.ui_nodes)
            + [f"ocr:{item.text}" for item in observation.ocr_texts[:80]],
            "locator_candidates": _locator_candidates(observation.ui_nodes)
            + [
                {
                    "ocr_text": item.text,
                    "confidence": round(item.confidence, 4),
                    "bounds": to_jsonable(item.bounds),
                }
                for item in observation.ocr_texts[:80]
            ],
            "warnings": capture_warnings,
            "artifacts": [to_jsonable(ref) for ref in refs],
        }

    def _save_manifest(self, manifest: dict[str, Any]) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.manifest_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(to_jsonable(manifest), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.manifest_path)


def run_manual_flow_recording(
    settings: RuntimeSettings,
    *,
    device_id: str,
    flow_name: str,
    app_label: str | None = None,
) -> int:
    """连接一台配置设备并运行交互式流程记录。"""

    device = next(
        (item for item in settings.devices if item.descriptor.device_id == device_id),
        None,
    )
    if device is None:
        raise ValueError(f"配置中没有设备: {device_id}")
    clock = SystemClock()
    events = ConsoleEventSink(
        EventFilter(min_level=EventLevel(settings.logging.console_level))
    )
    session = DeviceSession(
        device.descriptor,
        AirtestPocoDeviceFactory(),
        events,
        clock,
        settings.retry,
    )
    safe_device = _safe_name(device_id)
    recording_id = f"{clock.now().strftime('%Y%m%d-%H%M%S')}-{_safe_name(flow_name)}-{uuid4().hex[:8]}"
    root = settings.artifact_dir / safe_device / "手动流程" / recording_id
    diagnostics = DiagnosticsService(session, LocalArtifactStore(root / "现场"))
    ocr_engine = (
        create_ocr_engine(settings.vision.ocr_engine, settings.vision.ocr_language)
        if settings.vision.enable_ocr
        else None
    )
    recorder = ManualFlowRecorder(
        session=session,
        diagnostics=diagnostics,
        manifest_path=root / "manifest.json",
        flow_name=flow_name,
        app_label=app_label,
        ocr_engine=ocr_engine,
    )
    lease = DeviceLease(settings.state_dir / ".locks" / f"{safe_device}.lock")
    try:
        with lease:
            try:
                if not session.connect():
                    return 2
                return recorder.run()
            finally:
                session.close()
    except DeviceBusyError as error:
        print(str(error))
        return 3


def _stable_markers(nodes: tuple[UiNode, ...]) -> list[str]:
    markers: list[str] = []
    seen: set[str] = set()
    for node in nodes:
        values = (
            f"id:{node.resource_id}" if node.resource_id else None,
            f"text:{node.text}" if node.text else None,
            f"desc:{node.description}" if node.description else None,
        )
        for marker in values:
            if marker is None or marker in seen:
                continue
            seen.add(marker)
            markers.append(marker)
            if len(markers) >= 160:
                return markers
    return markers


def _locator_candidates(nodes: tuple[UiNode, ...]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for node in nodes:
        if not (node.resource_id or node.text or node.description):
            continue
        candidates.append(
            {
                "resource_id": node.resource_id,
                "text": node.text,
                "description": node.description,
                "class_name": node.class_name,
                "clickable": node.clickable,
                "selected": node.selected,
                "bounds": to_jsonable(node.bounds),
            }
        )
        if len(candidates) >= 80:
            break
    return candidates


def _transition(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_markers = set(before.get("markers", ()))
    after_markers = set(after.get("markers", ()))
    before_activity = before.get("activity")
    after_activity = after.get("activity")
    added = sorted(after_markers - before_markers)
    removed = sorted(before_markers - after_markers)
    return {
        "changed": before_activity != after_activity or bool(added or removed),
        "activity_changed": before_activity != after_activity,
        "before_activity": before_activity,
        "after_activity": after_activity,
        "added_marker_count": len(added),
        "removed_marker_count": len(removed),
        "added_markers": added[:60],
        "removed_markers": removed[:60],
    }


def _safe_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_." else "_" for char in value)
    return cleaned[:60] or "flow"
