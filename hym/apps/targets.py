from __future__ import annotations

from typing import Any, Mapping

from hym.core.models import Point, Rect
from hym.core.targets import LocatorKind, LocatorSpec, TargetSpec


def target(
    target_id: str,
    *locators: LocatorSpec,
    required: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> TargetSpec:
    """声明一个业务目标；多个 locator 是备选关系，任意一个命中即可。"""

    return TargetSpec(target_id, tuple(locators), required=required, metadata=metadata or {})


def activity_locator(
    strategy_id: str,
    activity_pattern: str,
    *,
    package_name: str | None = None,
    priority: int = 5,
) -> LocatorSpec:
    """按当前 Activity 识别页面，不读取 UI 树。"""

    options: dict[str, Any] = {"mode": "regex"}
    if package_name is not None:
        options["package_name"] = package_name
    return LocatorSpec(
        strategy_id,
        LocatorKind.ACTIVITY,
        activity_pattern,
        priority=priority,
        options=options,
    )


def id_locator(strategy_id: str, resource_id: str, priority: int = 10) -> LocatorSpec:
    """按完整 resource-id 定位；通常写成包名前缀加控件 ID。"""

    return LocatorSpec(strategy_id, LocatorKind.UI_ID, resource_id, priority=priority)


def text_locator(
    strategy_id: str,
    text: str,
    *,
    priority: int = 20,
    contains: bool = False,
    region: Rect | None = None,
) -> LocatorSpec:
    if contains:
        return LocatorSpec(
            strategy_id,
            LocatorKind.UI_QUERY,
            region=region,
            priority=priority,
            options={"contains_text": text},
        )
    return LocatorSpec(strategy_id, LocatorKind.UI_TEXT, text, region=region, priority=priority)


def desc_locator(strategy_id: str, description: str, priority: int = 20) -> LocatorSpec:
    return LocatorSpec(strategy_id, LocatorKind.UI_DESC, description, priority=priority)


def regex_locator(
    strategy_id: str,
    pattern: str,
    priority: int = 30,
    region: Rect | None = None,
) -> LocatorSpec:
    return LocatorSpec(strategy_id, LocatorKind.UI_REGEX, pattern, region=region, priority=priority)


def query_locator(
    strategy_id: str,
    *,
    priority: int = 60,
    options: Mapping[str, Any] | None = None,
) -> LocatorSpec:
    return LocatorSpec(
        strategy_id,
        LocatorKind.UI_QUERY,
        priority=priority,
        options=options or {},
    )


def layout_locator(
    strategy_id: str,
    class_name: str,
    *,
    position: tuple[float, float] | None = None,
    size: tuple[float, float] | None = None,
    parent_class: str | None = None,
    position_tolerance: float = 0.1,
    size_tolerance: float = 0.1,
    priority: int = 60,
    pick: str = "highest",
    extra: Mapping[str, Any] | None = None,
) -> LocatorSpec:
    options: dict[str, Any] = {
        "class_name": class_name,
        "position_tolerance": position_tolerance,
        "size_tolerance": size_tolerance,
        "pick": pick,
    }
    if position is not None:
        options["position"] = position
    if size is not None:
        options["size"] = size
    if parent_class is not None:
        options["parent_class"] = parent_class
    options.update(extra or {})
    return LocatorSpec(strategy_id, LocatorKind.UI_QUERY, priority=priority, options=options)


def ocr_locator(
    strategy_id: str,
    text: str,
    *,
    priority: int = 80,
    mode: str = "contains",
    region: Rect | None = None,
    confidence: float = 0.72,
) -> LocatorSpec:
    return LocatorSpec(
        strategy_id,
        LocatorKind.OCR_TEXT,
        text,
        region=region,
        min_confidence=confidence,
        priority=priority,
        options={"mode": mode},
    )


def image_locator(
    strategy_id: str,
    image_path: str,
    *,
    priority: int = 70,
    confidence: float = 0.8,
    region: Rect | None = None,
) -> LocatorSpec:
    return LocatorSpec(
        strategy_id,
        LocatorKind.IMAGE,
        image_path,
        region=region,
        min_confidence=confidence,
        priority=priority,
    )


def coordinate_locator(strategy_id: str, point: Point, priority: int = 200) -> LocatorSpec:
    return LocatorSpec(
        strategy_id,
        LocatorKind.COORDINATE,
        priority=priority,
        options={"point": (point.x, point.y)},
    )
