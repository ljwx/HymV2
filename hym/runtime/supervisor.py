from __future__ import annotations

import multiprocessing
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from hym.core.config import DeviceRunSettings, load_runtime_settings
from hym.runtime.runner import run_device_from_config


@dataclass(slots=True)
class _WorkerSlot:
    device: DeviceRunSettings
    process: multiprocessing.Process | None = None
    restarts: int = 0
    finished: bool = False
    exit_code: int | None = None


def run_supervised(
    config_path: str | Path,
    *,
    once: bool,
    device_ids: Iterable[str] | None = None,
    app_ids: Iterable[str] | None = None,
) -> int:
    """为每台设备启动独立进程，异常退出时做有限重启。"""

    path = Path(config_path).resolve()
    settings = load_runtime_settings(path)
    selected = set(device_ids or ())
    selected_apps = set(app_ids or ())
    devices = tuple(
        device
        for device in settings.devices
        if (not selected or device.descriptor.device_id in selected)
        and (
            not selected_apps
            or any(app.enabled and app.app_id in selected_apps for app in device.apps)
        )
    )
    if not devices:
        raise ValueError("没有匹配到需要运行的设备或已启用 App")

    process_context = multiprocessing.get_context("spawn")
    slots = [_WorkerSlot(device) for device in devices]
    for slot in slots:
        _start_worker(process_context, slot, path, once, selected_apps)

    try:
        while any(not slot.finished for slot in slots):
            for slot in slots:
                if slot.finished or slot.process is None or slot.process.is_alive():
                    continue
                slot.process.join(timeout=0.2)
                slot.exit_code = slot.process.exitcode
                if once and slot.exit_code == 0:
                    slot.finished = True
                elif slot.restarts < settings.processes.restart_limit:
                    slot.restarts += 1
                    _start_worker(process_context, slot, path, once, selected_apps)
                else:
                    slot.finished = True
                    print(
                        f"级别=错误 事件=工作进程结束 设备={slot.device.descriptor.device_id} "
                        f"消息=\"工作进程退出且已达到重启上限，退出码: {slot.exit_code}\"",
                        flush=True,
                    )
            if any(not slot.finished for slot in slots):
                time.sleep(settings.processes.monitor_interval_seconds)
    except KeyboardInterrupt:
        print("级别=信息 事件=运行停止 消息=\"收到停止指令，正在关闭设备进程\"", flush=True)
        for slot in slots:
            if slot.process is not None and slot.process.is_alive():
                slot.process.terminate()
        for slot in slots:
            if slot.process is not None:
                slot.process.join(timeout=10)
        return 130
    return 0 if all(slot.exit_code == 0 for slot in slots) else 2


def _worker_entry(
    config_path: str,
    device_id: str,
    once: bool,
    app_ids: tuple[str, ...],
) -> None:
    raise SystemExit(run_device_from_config(config_path, device_id, once, app_ids=app_ids))


def _start_worker(
    process_context,
    slot: _WorkerSlot,
    config_path: Path,
    once: bool,
    app_ids: Iterable[str],
) -> None:
    selected_apps = tuple(app_ids)
    process = process_context.Process(
        target=_worker_entry,
        args=(str(config_path), slot.device.descriptor.device_id, once, selected_apps),
        name=f"hym-{_safe_id(slot.device.descriptor.device_id)}",
    )
    process.start()
    slot.process = process
    print(
        f"级别=信息 事件=工作进程启动 设备={slot.device.descriptor.device_id} "
        f"消息=\"设备工作进程已启动，进程号: {process.pid}\"",
        flush=True,
    )


def _safe_id(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_." else "_" for char in value)
