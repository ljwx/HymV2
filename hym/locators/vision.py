from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

from hym.core.models import ImageFrame, ImageMatch, OcrText, Point, Rect


class OpenCvTemplateMatcher:
    """按需加载 OpenCV；未配置图片定位时不会产生额外开销。"""

    def __init__(self, resource_root: str | Path) -> None:
        self._resource_root = Path(resource_root)

    def match(
        self,
        frame: ImageFrame,
        template_id: str,
        region: Rect | None = None,
    ) -> tuple[ImageMatch, ...]:
        import cv2

        image = _frame_to_bgr(frame)
        template = cv2.imread(str(self._resource_root / template_id), cv2.IMREAD_COLOR)
        if template is None:
            return ()

        left, top, right, bottom = _pixel_region(frame, region)
        search = image[top:bottom, left:right]
        if template.shape[0] > search.shape[0] or template.shape[1] > search.shape[1]:
            return ()
        result = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
        _, confidence, _, location = cv2.minMaxLoc(result)
        x, y = location
        height, width = template.shape[:2]
        bounds = Rect(
            (left + x) / frame.width,
            (top + y) / frame.height,
            (left + x + width) / frame.width,
            (top + y + height) / frame.height,
        )
        return (ImageMatch(template_id, bounds, float(confidence), "opencv"),)


class PaddleOcrEngine:
    """可选 PaddleOCR 适配器，只有真正使用 OCR 目标时才初始化模型。"""

    def __init__(self, *, lang: str = "ch", engine: Any | None = None) -> None:
        self._lang = lang
        self._engine = engine

    def recognize(self, frame: ImageFrame, region: Rect | None = None) -> tuple[OcrText, ...]:
        if self._engine is None:
            from paddleocr import PaddleOCR

            self._engine = PaddleOCR(use_angle_cls=False, lang=self._lang, show_log=False)
        image = _frame_to_bgr(frame)
        left, top, right, bottom = _pixel_region(frame, region)
        cropped = image[top:bottom, left:right]
        raw = self._engine.ocr(cropped, cls=False)
        return tuple(_parse_legacy_ocr(raw, frame, left, top))


class MacOsVisionOcrEngine:
    """调用 macOS Vision，编译产物按源码哈希缓存在系统临时目录。"""

    def __init__(self, *, language: str = "zh-Hans", recognition_level: str = "accurate") -> None:
        if recognition_level not in {"fast", "accurate"}:
            raise ValueError("macOS Vision 识别级别必须是 fast 或 accurate")
        self._language = language
        self._recognition_level = recognition_level
        self._source = Path(__file__).with_name("macos_vision_ocr.swift")
        self._binary: Path | None = None

    def recognize(self, frame: ImageFrame, region: Rect | None = None) -> tuple[OcrText, ...]:
        binary = self._ensure_binary()
        image = _frame_to_bgr(frame)
        left, top, right, bottom = _pixel_region(frame, region)
        cropped = image[top:bottom, left:right]

        import cv2

        succeeded, encoded = cv2.imencode(".png", cropped)
        if not succeeded:
            raise RuntimeError("OCR 临时图片编码失败")
        temporary_path = ""
        try:
            with tempfile.NamedTemporaryFile(prefix="hym-ocr-", suffix=".png", delete=False) as file:
                temporary_path = file.name
                file.write(encoded.tobytes())
            result = subprocess.run(
                [str(binary), temporary_path, self._language, self._recognition_level],
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
            )
            raw = json.loads(result.stdout)
            return tuple(_parse_macos_vision_ocr(raw, frame, left, top, right - left, bottom - top))
        finally:
            if temporary_path:
                Path(temporary_path).unlink(missing_ok=True)

    def _ensure_binary(self) -> Path:
        if self._binary is not None and self._binary.exists():
            return self._binary
        if platform.system() != "Darwin":
            raise RuntimeError("macOS Vision OCR 只能在 macOS 上运行")
        compiler = shutil.which("swiftc")
        if compiler is None:
            raise RuntimeError("没有找到 swiftc，无法启用 macOS Vision OCR")
        digest = hashlib.sha256(self._source.read_bytes()).hexdigest()[:12]
        binary = Path(tempfile.gettempdir()) / f"hym-macos-vision-ocr-{digest}"
        if not binary.exists():
            subprocess.run(
                [compiler, str(self._source), "-O", "-o", str(binary)],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
        self._binary = binary
        return binary


def create_ocr_engine(engine_name: str, language: str):
    if engine_name == "paddle":
        return PaddleOcrEngine(lang=language)
    if engine_name == "macos_vision":
        return MacOsVisionOcrEngine(language=language)
    raise ValueError(f"未知 OCR 引擎: {engine_name}")


def _parse_legacy_ocr(raw: Any, frame: ImageFrame, offset_x: int, offset_y: int):
    pages = raw if isinstance(raw, list) else []
    lines = pages[0] if pages and isinstance(pages[0], list) else pages
    for line in lines or ():
        if not isinstance(line, (tuple, list)) or len(line) < 2:
            continue
        polygon, text_info = line[0], line[1]
        if not isinstance(text_info, (tuple, list)) or len(text_info) < 2:
            continue
        points = [point for point in polygon if isinstance(point, (tuple, list)) and len(point) >= 2]
        if not points:
            continue
        xs = [float(point[0]) + offset_x for point in points]
        ys = [float(point[1]) + offset_y for point in points]
        yield OcrText(
            text=str(text_info[0]),
            bounds=Rect(min(xs) / frame.width, min(ys) / frame.height, max(xs) / frame.width, max(ys) / frame.height),
            confidence=float(text_info[1]),
            engine="paddleocr",
        )


def _parse_macos_vision_ocr(
    raw: Any,
    frame: ImageFrame,
    offset_x: int,
    offset_y: int,
    crop_width: int,
    crop_height: int,
):
    for item in raw if isinstance(raw, list) else ():
        if not isinstance(item, dict) or not str(item.get("text", "")).strip():
            continue
        try:
            left = (offset_x + float(item["left"]) * crop_width) / frame.width
            top = (offset_y + float(item["top"]) * crop_height) / frame.height
            right = (offset_x + float(item["right"]) * crop_width) / frame.width
            bottom = (offset_y + float(item["bottom"]) * crop_height) / frame.height
            if left >= right or top >= bottom:
                continue
            yield OcrText(
                text=str(item["text"]),
                bounds=Rect(left, top, right, bottom),
                confidence=float(item.get("confidence", 0.0)),
                engine="macos_vision",
            )
        except (KeyError, TypeError, ValueError):
            continue


def _frame_to_bgr(frame: ImageFrame):
    import cv2
    import numpy as np

    channels = {"GRAY": 1, "BGR": 3, "BGRA": 4}.get(frame.pixel_format)
    if channels is None:
        raise ValueError(f"不支持的像素格式: {frame.pixel_format}")
    shape = (frame.height, frame.width) if channels == 1 else (frame.height, frame.width, channels)
    image = np.frombuffer(frame.data, dtype=np.uint8).reshape(shape)
    if frame.pixel_format == "GRAY":
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if frame.pixel_format == "BGRA":
        return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    return image


def _pixel_region(frame: ImageFrame, region: Rect | None) -> tuple[int, int, int, int]:
    if region is None:
        return 0, 0, frame.width, frame.height
    return (
        round(region.left * frame.width),
        round(region.top * frame.height),
        round(region.right * frame.width),
        round(region.bottom * frame.height),
    )
