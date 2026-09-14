"""平台无关的领域模型与接口。"""

from hym.core.models import (
    ActionResult,
    ActionStatus,
    AppIdentity,
    DeviceDescriptor,
    HealthReport,
    HealthState,
    Observation,
    ObservationRequest,
    ObservationResult,
    Point,
    Rect,
    StepResult,
    UiTreeSource,
    WorkflowResult,
    WorkflowStatus,
)
from hym.core.targets import LocatorKind, LocatorSpec, ResolveResult, TargetSpec
from hym.core.pages import ObservationProfile, PageMatchResult, PageMatchStatus, PageSpec

__all__ = [
    "ActionResult",
    "ActionStatus",
    "AppIdentity",
    "DeviceDescriptor",
    "HealthReport",
    "HealthState",
    "LocatorKind",
    "LocatorSpec",
    "Observation",
    "ObservationRequest",
    "ObservationResult",
    "ObservationProfile",
    "PageMatchResult",
    "PageMatchStatus",
    "PageSpec",
    "Point",
    "Rect",
    "ResolveResult",
    "StepResult",
    "TargetSpec",
    "UiTreeSource",
    "WorkflowResult",
    "WorkflowStatus",
]
