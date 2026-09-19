from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable

from hym.core.models import (
    ActionResult,
    AppIdentity,
    ArtifactRef,
    DeviceDescriptor,
    HealthReport,
    ImageFrame,
    ImageMatch,
    Observation,
    ObservationRequest,
    ObservationResult,
    Point,
    OcrText,
    Rect,
    SwipeGesture,
    SystemKey,
)
from hym.core.targets import LocatorKind, ResolveResult, TargetSpec

if TYPE_CHECKING:
    from hym.core.control import DeviceControlState, RemoteCommand
    from hym.core.events import AutomationEvent

T = TypeVar("T")


@runtime_checkable
class DevicePort(Protocol):
    """屏蔽 Airtest、无障碍等底层差异的设备能力。"""

    @property
    def descriptor(self) -> DeviceDescriptor: ...

    def connect(self) -> ActionResult: ...

    def disconnect(self) -> ActionResult: ...

    def health_check(self) -> HealthReport: ...

    def start_app(self, app: AppIdentity) -> ActionResult: ...

    def stop_app(self, app: AppIdentity) -> ActionResult: ...

    def observe(self, request: ObservationRequest) -> ObservationResult: ...

    def tap(self, point: Point, duration_seconds: float = 0.1) -> ActionResult: ...

    def swipe(self, gesture: SwipeGesture) -> ActionResult: ...

    def press(self, key: SystemKey) -> ActionResult: ...

    def input_text(self, value: str) -> ActionResult: ...


@runtime_checkable
class DeviceFactoryPort(Protocol):
    """按设备描述创建独立会话，便于一台设备对应一个进程。"""

    def create(self, descriptor: DeviceDescriptor) -> DevicePort: ...


@runtime_checkable
class LocatorPort(Protocol):
    """只根据一次页面观察定位目标，不直接操作设备。"""

    def resolve(self, target: TargetSpec, observation: Observation) -> ResolveResult: ...

    def supports(self, kind: LocatorKind) -> bool: ...


@runtime_checkable
class OcrEnginePort(Protocol):
    """从截图区域返回文本和位置；实现可以是本地 OCR 或远端服务。"""

    def recognize(self, frame: ImageFrame, region: Rect | None = None) -> tuple[OcrText, ...]: ...


@runtime_checkable
class ImageMatcherPort(Protocol):
    """匹配单个图片模板，不限定具体视觉库。"""

    def match(
        self,
        frame: ImageFrame,
        template_id: str,
        region: Rect | None = None,
    ) -> tuple[ImageMatch, ...]: ...


@runtime_checkable
class EventSinkPort(Protocol):
    """接收结构化事件，输出方式由适配器决定。"""

    def emit(self, event: AutomationEvent) -> None: ...


@runtime_checkable
class StateStorePort(Protocol):
    """保存每日状态、任务进度等可恢复数据。"""

    def get(self, namespace: str, key: str, default: T | None = None) -> T | None: ...

    def set(self, namespace: str, key: str, value: Any) -> None: ...


@runtime_checkable
class ArtifactStorePort(Protocol):
    """保存截图、UI 树等体积较大的诊断产物。"""

    def save_bytes(
        self,
        *,
        kind: str,
        content: bytes,
        media_type: str,
        name_hint: str | None = None,
    ) -> ArtifactRef: ...


@runtime_checkable
class ClockPort(Protocol):
    def now(self) -> datetime: ...

    def sleep(self, seconds: float) -> None: ...


@runtime_checkable
class RandomPort(Protocol):
    """集中管理随机行为，测试时可注入固定序列。"""

    def random(self) -> float: ...

    def uniform(self, start: float, end: float) -> float: ...

    def normalvariate(self, center: float, stddev: float) -> float: ...

    def randint(self, start: int, end: int) -> int: ...

    def choice(self, items: Sequence[T]) -> T: ...


@runtime_checkable
class RemoteControlPort(Protocol):
    """屏蔽 HTTP 等传输细节，运行器只处理暂停状态和任务命令。"""

    def control(self, device_id: str) -> DeviceControlState: ...

    def acknowledge_pause(self, device_id: str) -> None: ...

    def claim_command(self, device_id: str) -> RemoteCommand | None: ...

    def complete_command(
        self,
        device_id: str,
        command_id: str,
        *,
        succeeded: bool,
        message: str,
    ) -> None: ...
