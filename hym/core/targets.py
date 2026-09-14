from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from hym.core.models import Point, Rect


class LocatorKind(str, Enum):
    UI_ID = "ui_id"
    UI_TEXT = "ui_text"
    UI_DESC = "ui_desc"
    UI_REGEX = "ui_regex"
    UI_QUERY = "ui_query"
    ACTIVITY = "activity"
    # 兼容早期代码属性名，新代码只使用平台无关名称。
    POCO_ID = UI_ID
    POCO_TEXT = UI_TEXT
    POCO_DESC = UI_DESC
    POCO_REGEX = UI_REGEX
    POCO_QUERY = UI_QUERY
    OCR_TEXT = "ocr_text"
    IMAGE = "image"
    ANCHOR_OFFSET = "anchor_offset"
    COORDINATE = "coordinate"
    CUSTOM = "custom"


class ResolveStatus(str, Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class LocatorSpec:
    """单个定位策略，可按目标独立排序和配置。"""

    strategy_id: str
    kind: LocatorKind
    query: str | None = None
    region: Rect | None = None
    min_confidence: float = 0.8
    priority: int = 100
    options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0 <= self.min_confidence <= 1:
            raise ValueError("定位置信度必须位于 0 到 1 之间")


@dataclass(frozen=True, slots=True)
class TargetSpec:
    """一个业务目标可以组合多种定位方式。"""

    target_id: str
    locators: tuple[LocatorSpec, ...]
    required: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.locators:
            raise ValueError("目标至少需要一种定位策略")


@dataclass(frozen=True, slots=True)
class ResolvedTarget:
    target_id: str
    strategy_id: str
    point: Point
    confidence: float
    observation_id: str
    bounds: Rect | None = None
    evidence: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResolveAttempt:
    strategy_id: str
    status: ResolveStatus
    elapsed_seconds: float
    message: str = ""
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class ResolveResult:
    status: ResolveStatus
    target: ResolvedTarget | None = None
    attempts: tuple[ResolveAttempt, ...] = ()
    message: str = ""

    @property
    def found(self) -> bool:
        return self.status is ResolveStatus.FOUND and self.target is not None
