from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ActionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    CANCELLED = "cancelled"


class HealthState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"


class WorkflowStatus(str, Enum):
    SUCCESS = "success"
    ALREADY_DONE = "already_done"
    SKIPPED = "skipped"
    PARTIAL = "partial"
    RETRYABLE_FAILURE = "retryable_failure"
    NO_PROGRESS = "no_progress"
    FATAL = "fatal"
    CANCELLED = "cancelled"


class SystemKey(str, Enum):
    BACK = "back"
    HOME = "home"
    APP_SWITCH = "app_switch"
    VOLUME_UP = "volume_up"
    VOLUME_DOWN = "volume_down"
    POWER = "power"


class UiTreeSource(str, Enum):
    """UI 树来源由目标声明，上层流程不依赖具体自动化框架。"""

    AUTO = "auto"
    INSTRUMENTATION = "instrumentation"
    ACCESSIBILITY = "accessibility"


@dataclass(frozen=True, slots=True)
class Point:
    """使用 0 到 1 的归一化屏幕坐标。"""

    x: float
    y: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.x) or not math.isfinite(self.y):
            raise ValueError("坐标必须是有限数值")
        if not 0 <= self.x <= 1 or not 0 <= self.y <= 1:
            raise ValueError("归一化坐标必须位于 0 到 1 之间")


@dataclass(frozen=True, slots=True)
class Rect:
    left: float
    top: float
    right: float
    bottom: float

    def __post_init__(self) -> None:
        values = (self.left, self.top, self.right, self.bottom)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("区域坐标必须是有限数值")
        if not all(0 <= value <= 1 for value in values):
            raise ValueError("归一化区域必须位于 0 到 1 之间")
        if self.left >= self.right or self.top >= self.bottom:
            raise ValueError("区域边界无效")

    @property
    def center(self) -> Point:
        return Point((self.left + self.right) / 2, (self.top + self.bottom) / 2)


@dataclass(frozen=True, slots=True)
class AppIdentity:
    app_id: str
    package_name: str
    display_name: str
    version: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DeviceDescriptor:
    device_id: str
    platform: str = "android"
    connection: str | None = None
    model: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ActivityInfo:
    package_name: str = ""
    activity_name: str = ""


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    artifact_id: str
    kind: str
    uri: str
    media_type: str | None = None
    sha256: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ImageFrame:
    """不依赖图像库的内存帧。"""

    width: int
    height: int
    data: bytes
    pixel_format: str = "BGR"

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("图像尺寸必须大于零")


@dataclass(frozen=True, slots=True)
class UiNode:
    node_id: str
    parent_id: str | None
    class_name: str | None = None
    resource_id: str | None = None
    text: str | None = None
    description: str | None = None
    bounds: Rect | None = None
    clickable: bool | None = None
    enabled: bool | None = None
    selected: bool | None = None
    visible: bool | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OcrText:
    text: str
    bounds: Rect
    confidence: float
    engine: str


@dataclass(frozen=True, slots=True)
class ImageMatch:
    template_id: str
    bounds: Rect
    confidence: float
    engine: str


@dataclass(frozen=True, slots=True)
class ObservationRequest:
    """按需采集数据，避免每次观察都执行截图。"""

    include_ui_tree: bool = True
    include_screenshot: bool = False
    screenshot_max_size: int | None = None
    ui_tree_source: UiTreeSource = UiTreeSource.AUTO


@dataclass(frozen=True, slots=True)
class Observation:
    """一次页面观察，所有定位器共享同一份基础数据。"""

    device_id: str
    activity: ActivityInfo
    observation_id: str = field(default_factory=lambda: uuid4().hex)
    captured_at: datetime = field(default_factory=utc_now)
    ui_nodes: tuple[UiNode, ...] = ()
    screenshot: ImageFrame | None = None
    ocr_texts: tuple[OcrText, ...] = ()
    image_matches: tuple[ImageMatch, ...] = ()
    artifacts: tuple[ArtifactRef, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ObservationResult:
    status: ActionStatus
    observation: Observation | None = None
    message: str = ""
    retryable: bool = False

    @property
    def succeeded(self) -> bool:
        return self.status is ActionStatus.SUCCESS and self.observation is not None


@dataclass(frozen=True, slots=True)
class HealthReport:
    state: HealthState
    checked_at: datetime = field(default_factory=utc_now)
    message: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ActionResult:
    """设备动作只返回中立结果，不向上暴露底层异常类型。"""

    operation: str
    status: ActionStatus
    started_at: datetime
    finished_at: datetime
    message: str = ""
    retryable: bool = False
    data: Mapping[str, Any] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.status is ActionStatus.SUCCESS

    @classmethod
    def success(
        cls,
        operation: str,
        *,
        started_at: datetime | None = None,
        message: str = "",
        data: Mapping[str, Any] | None = None,
    ) -> ActionResult:
        started = started_at or utc_now()
        return cls(operation, ActionStatus.SUCCESS, started, utc_now(), message, False, data or {})

    @classmethod
    def failure(
        cls,
        operation: str,
        message: str,
        *,
        started_at: datetime | None = None,
        retryable: bool = True,
        status: ActionStatus = ActionStatus.FAILED,
        data: Mapping[str, Any] | None = None,
    ) -> ActionResult:
        started = started_at or utc_now()
        return cls(operation, status, started, utc_now(), message, retryable, data or {})


@dataclass(frozen=True, slots=True)
class SwipeGesture:
    start: Point
    end: Point
    duration_seconds: float

    def __post_init__(self) -> None:
        if self.duration_seconds <= 0:
            raise ValueError("滑动时长必须大于零")


@dataclass(frozen=True, slots=True)
class StepResult:
    step_id: str
    status: WorkflowStatus
    started_at: datetime
    finished_at: datetime
    attempts: int = 1
    message: str = ""
    outputs: Mapping[str, Any] = field(default_factory=dict)
    artifacts: tuple[ArtifactRef, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    workflow_id: str
    status: WorkflowStatus
    started_at: datetime
    finished_at: datetime
    steps: tuple[StepResult, ...] = ()
    outputs: Mapping[str, Any] = field(default_factory=dict)
