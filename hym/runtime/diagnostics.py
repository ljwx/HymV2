from __future__ import annotations

import json
from dataclasses import asdict, replace

from hym.core.events import to_jsonable
from hym.core.models import ArtifactRef, ImageFrame, Observation, ObservationRequest, UiTreeSource
from hym.core.ports import ArtifactStorePort
from hym.runtime.session import DeviceSession


class DiagnosticsService:
    """在关键失败处保存页面快照，不在正常轮询中持续落盘。"""

    def __init__(self, session: DeviceSession, artifacts: ArtifactStorePort) -> None:
        self._session = session
        self._artifacts = artifacts

    def capture(
        self,
        name: str,
        observation: Observation | None = None,
        metadata: dict | None = None,
    ) -> tuple[ArtifactRef, ...]:
        if observation is None:
            result = self._session.observe(
                ObservationRequest(
                    include_ui_tree=True,
                    include_screenshot=True,
                    ui_tree_source=UiTreeSource.AUTO,
                )
            )
            observation = result.observation if result.succeeded else None
        if observation is None:
            return ()

        # 先移除二进制帧，避免 asdict 深拷贝整张截图。
        safe_observation = asdict(replace(observation, screenshot=None))
        tree_content = json.dumps(
            to_jsonable(safe_observation),
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        refs = [
            self._artifacts.save_bytes(
                kind="页面结构",
                content=tree_content,
                media_type="application/json",
                name_hint=name,
            )
        ]
        if metadata:
            refs.append(
                self._artifacts.save_bytes(
                    kind="执行上下文",
                    content=json.dumps(to_jsonable(metadata), ensure_ascii=False, indent=2).encode("utf-8"),
                    media_type="application/json",
                    name_hint=name,
                )
            )
        if observation.screenshot is not None:
            content, media_type = _encode_frame(observation.screenshot)
            refs.append(
                self._artifacts.save_bytes(
                    kind="页面截图",
                    content=content,
                    media_type=media_type,
                    name_hint=name,
                )
            )
        return tuple(refs)


def _encode_frame(frame: ImageFrame) -> tuple[bytes, str]:
    try:
        import cv2
        import numpy as np

        channels = {"GRAY": 1, "BGR": 3, "BGRA": 4}.get(frame.pixel_format)
        if channels is None:
            raise ValueError("不支持的像素格式")
        shape = (frame.height, frame.width) if channels == 1 else (frame.height, frame.width, channels)
        image = np.frombuffer(frame.data, dtype=np.uint8).reshape(shape)
        success, encoded = cv2.imencode(".png", image)
        if success:
            return encoded.tobytes(), "image/png"
    except (ImportError, ValueError):
        pass
    return frame.data, "application/octet-stream"
