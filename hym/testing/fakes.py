from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Iterable
from uuid import uuid4

from hym.core.models import (
    ActionResult,
    ActionStatus,
    ActivityInfo,
    AppIdentity,
    ArtifactRef,
    DeviceDescriptor,
    HealthReport,
    HealthState,
    Observation,
    ObservationRequest,
    ObservationResult,
    Point,
    SwipeGesture,
    SystemKey,
)
from hym.core.targets import ResolveResult, ResolveStatus, TargetSpec


@dataclass(frozen=True, slots=True)
class RecordedOperation:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


class FakeDevice:
    """按脚本返回结果，并记录所有设备操作。"""

    def __init__(
        self,
        descriptor: DeviceDescriptor,
        *,
        observations: Iterable[ObservationResult] = (),
    ) -> None:
        self._descriptor = descriptor
        self.operations: list[RecordedOperation] = []
        self._observations: Deque[ObservationResult] = deque(observations)
        self._scripted_results: dict[str, Deque[ActionResult]] = defaultdict(deque)
        self._connected = False

    @property
    def descriptor(self) -> DeviceDescriptor:
        return self._descriptor

    def script_action(self, operation: str, *results: ActionResult) -> None:
        self._scripted_results[operation].extend(results)

    def queue_observation(self, result: ObservationResult) -> None:
        self._observations.append(result)

    def _action(self, operation: str, **arguments: Any) -> ActionResult:
        self.operations.append(RecordedOperation(operation, arguments))
        scripted = self._scripted_results[operation]
        if scripted:
            return scripted.popleft()
        return ActionResult.success(operation)

    def connect(self) -> ActionResult:
        result = self._action("connect")
        self._connected = result.succeeded
        return result

    def disconnect(self) -> ActionResult:
        result = self._action("disconnect")
        if result.succeeded:
            self._connected = False
        return result

    def health_check(self) -> HealthReport:
        self.operations.append(RecordedOperation("health_check"))
        state = HealthState.HEALTHY if self._connected else HealthState.DISCONNECTED
        return HealthReport(state=state)

    def start_app(self, app: AppIdentity) -> ActionResult:
        return self._action("start_app", app_id=app.app_id, package_name=app.package_name)

    def stop_app(self, app: AppIdentity) -> ActionResult:
        return self._action("stop_app", app_id=app.app_id, package_name=app.package_name)

    def observe(self, request: ObservationRequest) -> ObservationResult:
        self.operations.append(RecordedOperation("observe", {"request": request}))
        if self._observations:
            return self._observations.popleft()
        return ObservationResult(
            status=ActionStatus.SUCCESS,
            observation=Observation(device_id=self.descriptor.device_id, activity=ActivityInfo()),
        )

    def tap(self, point: Point, duration_seconds: float = 0.1) -> ActionResult:
        return self._action("tap", point=point, duration_seconds=duration_seconds)

    def swipe(self, gesture: SwipeGesture) -> ActionResult:
        return self._action("swipe", gesture=gesture)

    def press(self, key: SystemKey) -> ActionResult:
        return self._action("press", key=key)

    def input_text(self, value: str) -> ActionResult:
        return self._action("input_text", text_length=len(value))


class FakeDeviceFactory:
    def __init__(self) -> None:
        self.created: list[FakeDevice] = []

    def create(self, descriptor: DeviceDescriptor) -> FakeDevice:
        device = FakeDevice(descriptor)
        self.created.append(device)
        return device


class FakeLocator:
    def __init__(self) -> None:
        self._results: dict[str, Deque[ResolveResult]] = defaultdict(deque)
        self.calls: list[tuple[TargetSpec, Observation]] = []

    def script(self, target_id: str, *results: ResolveResult) -> None:
        self._results[target_id].extend(results)

    def resolve(self, target: TargetSpec, observation: Observation) -> ResolveResult:
        self.calls.append((target, observation))
        results = self._results[target.target_id]
        if results:
            return results.popleft()
        return ResolveResult(status=ResolveStatus.NOT_FOUND, message="未配置定位结果")


class InMemoryStateStore:
    def __init__(self) -> None:
        self._values: dict[tuple[str, str], Any] = {}

    def get(self, namespace: str, key: str, default=None):
        return self._values.get((namespace, key), default)

    def set(self, namespace: str, key: str, value: Any) -> None:
        self._values[(namespace, key)] = value


class FakeClock:
    def __init__(self, current: datetime | None = None) -> None:
        self.current = current or datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.sleeps: list[float] = []

    def now(self) -> datetime:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.current += timedelta(seconds=seconds)


class DeterministicRandom:
    """始终选择范围中点，适合验证不稳定流程。"""

    def random(self) -> float:
        return 0.5

    def uniform(self, start: float, end: float) -> float:
        return (start + end) / 2

    def normalvariate(self, center: float, stddev: float) -> float:
        return center

    def randint(self, start: int, end: int) -> int:
        return start

    def choice(self, items):
        return items[0]


class InMemoryArtifactStore:
    def __init__(self) -> None:
        self.items: list[tuple[str, bytes, str, str | None]] = []

    def save_bytes(
        self,
        *,
        kind: str,
        content: bytes,
        media_type: str,
        name_hint: str | None = None,
    ) -> ArtifactRef:
        self.items.append((kind, content, media_type, name_hint))
        return ArtifactRef(uuid4().hex, kind, f"memory://{len(self.items)}", media_type)
