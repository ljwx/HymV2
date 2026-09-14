from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from hym.core.config import RetrySettings
from hym.core.events import AutomationEvent, EventLevel
from hym.core.models import (
    ActionResult,
    ActionStatus,
    AppIdentity,
    DeviceDescriptor,
    HealthState,
    ObservationRequest,
    ObservationResult,
    Point,
    SwipeGesture,
    SystemKey,
)
from hym.core.ports import ClockPort, DeviceFactoryPort, DevicePort, EventSinkPort


class DeviceSession:
    """维持长连接，仅在健康检查或动作失败后重连。"""

    def __init__(
        self,
        descriptor: DeviceDescriptor,
        factory: DeviceFactoryPort,
        events: EventSinkPort,
        clock: ClockPort,
        retry: RetrySettings,
    ) -> None:
        self.descriptor = descriptor
        self._factory = factory
        self._events = events
        self._clock = clock
        self._retry = retry
        self._device: DevicePort | None = None
        self._trace_id = uuid4().hex
        self._last_health_check = None

    @property
    def device(self) -> DevicePort:
        if self._device is None:
            self._device = self._factory.create(self.descriptor)
        return self._device

    def connect(self) -> bool:
        for attempt in range(1, self._retry.connect_attempts + 1):
            self._emit(
                "device.connect.started",
                "设备连接开始",
                f"正在连接设备，第 {attempt} 次尝试",
                status="started",
                data={"attempt": attempt},
            )
            result = self.device.connect()
            if result.succeeded:
                self._last_health_check = self._clock.now()
                self._emit(
                    "device.connect.succeeded",
                    "设备连接成功",
                    "设备连接已建立",
                    status="success",
                    data={"attempt": attempt},
                )
                return True
            self._emit(
                "device.connect.failed",
                "设备连接失败",
                f"设备连接失败: {result.message or '未知原因'}",
                level=EventLevel.WARNING,
                status=result.status.value,
                data={"attempt": attempt, "retryable": result.retryable},
            )
            if attempt < self._retry.connect_attempts:
                self._clock.sleep(self._retry.connect_backoff_seconds * attempt)
                self._replace_device()
        return False

    def ensure_healthy(self) -> bool:
        if self._device is None:
            return self.connect()
        now = self._clock.now()
        if self._last_health_check is not None:
            elapsed = (now - self._last_health_check).total_seconds()
            if self._retry.health_check_interval_seconds == 0 or elapsed < self._retry.health_check_interval_seconds:
                return True
        health = self.device.health_check()
        if health.state is HealthState.HEALTHY:
            self._last_health_check = now
            return True
        self._emit(
            "device.health.degraded",
            "设备连接异常",
            f"健康检查异常，准备重连: {health.message or health.state.value}",
            level=EventLevel.WARNING,
            status="failed",
            data={"health_state": health.state.value, **health.details},
        )
        return self.reconnect()

    def reconnect(self) -> bool:
        for attempt in range(1, self._retry.reconnect_attempts + 1):
            self._emit(
                "device.reconnect.started",
                "设备重新连接",
                f"正在重新连接设备，第 {attempt} 次尝试",
                level=EventLevel.WARNING,
                status="started",
                data={"attempt": attempt},
            )
            self._replace_device()
            result = self.device.connect()
            if result.succeeded:
                self._last_health_check = self._clock.now()
                self._emit(
                    "device.reconnect.succeeded",
                    "设备重连成功",
                    "设备连接已经恢复",
                    status="success",
                    data={"attempt": attempt},
                )
                return True
            if attempt < self._retry.reconnect_attempts:
                self._clock.sleep(self._retry.connect_backoff_seconds * attempt)
        self._emit(
            "device.reconnect.failed",
            "设备重连失败",
            "设备连接未能恢复，本轮任务将结束",
            level=EventLevel.ERROR,
            status="failed",
        )
        return False

    def close(self) -> None:
        if self._device is None:
            return
        result = self._device.disconnect()
        self._emit(
            "device.disconnect.finished",
            "设备连接关闭",
            "设备连接已关闭" if result.succeeded else f"关闭连接失败: {result.message}",
            level=EventLevel.INFO if result.succeeded else EventLevel.WARNING,
            status=result.status.value,
        )
        self._device = None
        self._last_health_check = None

    def observe(self, request: ObservationRequest) -> ObservationResult:
        last_result = ObservationResult(ActionStatus.UNAVAILABLE, message="设备连接不可用", retryable=True)
        for attempt in range(self._retry.observation_attempts):
            if not self.ensure_healthy():
                return last_result
            last_result = self.device.observe(request)
            if last_result.succeeded or not last_result.retryable:
                return last_result
            self._last_health_check = None
            if attempt + 1 < self._retry.observation_attempts and not self.reconnect():
                break
        return last_result

    def start_app(self, app: AppIdentity) -> ActionResult:
        return self._perform(lambda device: device.start_app(app), retry_action=True)

    def stop_app(self, app: AppIdentity) -> ActionResult:
        return self._perform(lambda device: device.stop_app(app), retry_action=False)

    def tap(self, point: Point, duration_seconds: float) -> ActionResult:
        return self._perform(lambda device: device.tap(point, duration_seconds), retry_action=False)

    def swipe(self, gesture: SwipeGesture) -> ActionResult:
        return self._perform(lambda device: device.swipe(gesture), retry_action=False)

    def press(self, key: SystemKey) -> ActionResult:
        return self._perform(lambda device: device.press(key), retry_action=False)

    def input_text(self, value: str) -> ActionResult:
        # 文本输入不是幂等动作，断线恢复后不能自动重放。
        return self._perform(lambda device: device.input_text(value), retry_action=False)

    def _perform(
        self,
        action: Callable[[DevicePort], ActionResult],
        *,
        retry_action: bool,
    ) -> ActionResult:
        if not self.ensure_healthy():
            return ActionResult.failure(
                "device_action",
                "设备连接不可用",
                status=ActionStatus.UNAVAILABLE,
            )
        result = action(self.device)
        if result.succeeded or not result.retryable:
            return result

        # 点击等非幂等动作只恢复连接，不自动重放，避免重复领奖或重复跳转。
        self._last_health_check = None
        recovered = self.reconnect()
        if recovered and retry_action:
            return action(self.device)
        return result

    def _replace_device(self) -> None:
        if self._device is not None:
            try:
                self._device.disconnect()
            except Exception:
                pass
        self._device = self._factory.create(self.descriptor)
        self._last_health_check = None

    def _emit(
        self,
        event_type: str,
        event_name: str,
        message: str,
        *,
        level: EventLevel = EventLevel.INFO,
        status: str | None = None,
        data: dict | None = None,
    ) -> None:
        self._events.emit(
            AutomationEvent(
                event_type=event_type,
                event_name=event_name,
                trace_id=self._trace_id,
                device_id=self.descriptor.device_id,
                level=level,
                message=message,
                status=status,
                data=data or {},
            )
        )
