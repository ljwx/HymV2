from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from hym.core.models import Observation, UiTreeSource
from hym.core.targets import LocatorKind, TargetSpec


@dataclass(frozen=True, slots=True)
class ObservationProfile:
    """声明页面观察偏好，避免业务流程依赖具体自动化实现。"""

    ui_tree_source: UiTreeSource = UiTreeSource.AUTO
    screenshot_max_size: int | None = None


@dataclass(frozen=True, slots=True)
class PageSpec:
    """页面由包名、Activity 和标记共同确认，minimum_markers 指定最少命中数。"""

    page_id: str
    package_name: str
    markers: tuple[TargetSpec, ...]
    forbidden_markers: tuple[TargetSpec, ...] = ()
    activity_patterns: tuple[str, ...] = ()
    minimum_markers: int = 1
    observation_profile: ObservationProfile | None = None

    def __post_init__(self) -> None:
        if not self.page_id:
            raise ValueError("页面 ID 不能为空")
        if not self.package_name:
            raise ValueError("页面包名不能为空")
        if not self.markers:
            raise ValueError("页面至少需要一个识别信号")
        if not 1 <= self.minimum_markers <= len(self.markers):
            raise ValueError("页面最少命中数必须位于识别信号数量范围内")
        for marker in (*self.markers, *self.forbidden_markers):
            if all(locator.kind is LocatorKind.COORDINATE for locator in marker.locators):
                raise ValueError(f"页面信号不能只使用固定坐标: {marker.target_id}")


class PageMatchStatus(str, Enum):
    MATCHED = "matched"
    NOT_MATCHED = "not_matched"
    OBSERVATION_FAILED = "observation_failed"


@dataclass(frozen=True, slots=True)
class PageMatchResult:
    page_id: str
    status: PageMatchStatus
    observation: Observation | None = None
    matched_markers: tuple[str, ...] = ()
    forbidden_markers: tuple[str, ...] = ()
    message: str = ""

    @property
    def matched(self) -> bool:
        return self.status is PageMatchStatus.MATCHED
