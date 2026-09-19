from __future__ import annotations

from collections import deque
from collections.abc import Callable
from datetime import date
from enum import Enum
from typing import TYPE_CHECKING, Any, Mapping
from uuid import uuid4

from hym.core.config import AppRunSettings
from hym.core.events import AutomationEvent, EventLevel
from hym.core.models import AppIdentity, ArtifactRef
from hym.core.pages import ObservationProfile
from hym.core.ports import EventSinkPort, OcrEnginePort, RandomPort, StateStorePort
from hym.core.randomness import bounded_normal_int
from hym.core.targets import ResolveResult
from hym.runtime.behavior import BehaviorTiming
from hym.runtime.diagnostics import DiagnosticsService
from hym.runtime.session import DeviceSession

if TYPE_CHECKING:
    from hym.runtime.actions import ActionController


class DailyActionStatus(str, Enum):
    NOT_STARTED = "not_started"
    PENDING_CONFIRMATION = "pending_confirmation"
    CONFIRMED = "confirmed"
    UNCERTAIN = "uncertain"


class AppContext:
    """一次 App 执行共享的依赖和链路信息。"""

    def __init__(
        self,
        *,
        app: AppIdentity,
        settings: AppRunSettings,
        session: DeviceSession,
        timing: BehaviorTiming,
        random_source: RandomPort,
        state: StateStorePort,
        events: EventSinkPort,
        diagnostics: DiagnosticsService,
        diagnostic_failure_threshold: int = 3,
        cycle_id: str | None = None,
        app_run_id: str | None = None,
        business_date: date | None = None,
        observation_profile: ObservationProfile | None = None,
        ocr: OcrEnginePort | None = None,
    ) -> None:
        self.app = app
        self.settings = settings
        self.session = session
        self.timing = timing
        self.random = random_source
        self.state = state
        self.events = events
        self.diagnostics = diagnostics
        self.diagnostic_failure_threshold = diagnostic_failure_threshold
        self.cycle_id = cycle_id or uuid4().hex
        self.app_run_id = app_run_id or uuid4().hex
        # 同一轮执行跨过午夜时，签到和余额仍归属轮次开始当天。
        self.business_date = business_date or self.timing.clock.now().astimezone().date()
        # 保留 trace_id 兼容已有日志消费者，新事件使用显式父子链路字段。
        self.trace_id = self.app_run_id
        self.step_run_id: str | None = None
        self.observation_profile = observation_profile or ObservationProfile()
        self.ocr = ocr
        self._actions: ActionController | None = None
        self.recent_locator_attempts: deque[dict[str, Any]] = deque(maxlen=50)
        self.runtime_progress: dict[str, dict[str, Any]] = {}
        self.safe_point_handler: Callable[[str, Mapping[str, Any]], None] | None = None

    @property
    def device_id(self) -> str:
        return self.session.descriptor.device_id

    @property
    def namespace(self) -> str:
        return f"{self.device_id}:{self.app.app_id}"

    @property
    def actions(self) -> ActionController:
        if self._actions is None:
            raise RuntimeError("动作控制器尚未绑定")
        return self._actions

    @actions.setter
    def actions(self, value: ActionController) -> None:
        self._actions = value

    def option(self, key: str, default: Any) -> Any:
        return self.settings.options.get(key, default)

    def sample_seconds(
        self,
        prefix: str,
        default_minimum: float,
        default_maximum: float,
        *,
        default_center: float | None = None,
        default_stddev: float | None = None,
        reward_wait: bool = False,
    ) -> float:
        """按统一的范围、中心值和标准差采样任务时间。"""

        minimum, center, maximum, stddev = self._range_options(
            prefix,
            default_minimum,
            default_maximum,
            default_center,
            default_stddev,
        )
        return self.timing.range_seconds(
            minimum,
            maximum,
            center=center,
            stddev=stddev,
            reward_wait=reward_wait,
        )

    def sample_count(
        self,
        prefix: str,
        default_minimum: int,
        default_maximum: int,
        *,
        default_center: float | None = None,
        default_stddev: float | None = None,
    ) -> int:
        """按统一的范围、中心值和标准差采样任务次数。"""

        minimum, center, maximum, stddev = self._range_options(
            prefix,
            float(default_minimum),
            float(default_maximum),
            default_center,
            default_stddev,
        )
        return bounded_normal_int(
            self.random,
            round(minimum),
            round(maximum),
            center=center,
            stddev=stddev,
        )

    def _range_options(
        self,
        prefix: str,
        default_minimum: float,
        default_maximum: float,
        default_center: float | None,
        default_stddev: float | None,
    ) -> tuple[float, float, float, float | None]:
        minimum = float(self.option(f"{prefix}_min", default_minimum))
        maximum = float(self.option(f"{prefix}_max", default_maximum))
        inferred_center = (minimum + maximum) / 2
        center = float(
            self.option(
                f"{prefix}_center",
                inferred_center if default_center is None else default_center,
            )
        )
        inferred_stddev = (maximum - minimum) / 6 if maximum > minimum else None
        configured_stddev = self.option(
            f"{prefix}_stddev",
            inferred_stddev if default_stddev is None else default_stddev,
        )
        stddev = None if configured_stddev is None else float(configured_stddev)
        return minimum, center, maximum, stddev

    def step_progress(self, step_id: str, **defaults: Any) -> dict[str, Any]:
        progress = self.runtime_progress.setdefault(step_id, dict(defaults))
        for key, value in defaults.items():
            progress.setdefault(key, value)
        return progress

    def clear_step_progress(self, step_id: str) -> None:
        self.runtime_progress.pop(step_id, None)

    def reach_safe_point(self, checkpoint: str, **data: Any) -> None:
        if self.safe_point_handler is not None:
            self.safe_point_handler(checkpoint, data)

    def daily_key(self, key: str) -> str:
        return f"daily:{self.business_date.isoformat()}:{key}"

    def daily_value(self, key: str, default: Any = None) -> Any:
        return self.state.get(self.namespace, self.daily_key(key), default)

    def mark_daily(self, key: str, value: Any) -> None:
        self.state.set(
            self.namespace,
            self.daily_key(key),
            {
                "value": value,
                "recorded_at": self.timing.clock.now().isoformat(),
            },
        )

    def daily_action_status(self, action_id: str) -> DailyActionStatus:
        value = self.state.get(self.namespace, self.daily_key(f"action:{action_id}"), {})
        if not isinstance(value, dict):
            return DailyActionStatus.NOT_STARTED
        try:
            return DailyActionStatus(str(value.get("status", DailyActionStatus.NOT_STARTED.value)))
        except ValueError:
            return DailyActionStatus.NOT_STARTED

    def mark_daily_action(
        self,
        action_id: str,
        status: DailyActionStatus,
        workflow_id: str | None = None,
        step_id: str | None = None,
        **details: Any,
    ) -> None:
        """在点击不可重复动作前落盘，进程中断后不会盲目补点。"""

        self.state.set(
            self.namespace,
            self.daily_key(f"action:{action_id}"),
            {
                "status": status.value,
                "updated_at": self.timing.clock.now().isoformat(),
                "details": details,
            },
        )
        self.emit(
            "action.checkpoint.changed",
            "动作检查点更新",
            f"动作 {action_id} 状态更新为 {_ACTION_STATUS_TEXT[status]}",
            workflow_id=workflow_id,
            step_id=step_id,
            status=status.value,
            data={"action_id": action_id, "action_status": status.value},
        )

    def record_locator_result(self, target_id: str, result: ResolveResult) -> None:
        self.recent_locator_attempts.append(
            {
                "target_id": target_id,
                "found": result.found,
                "message": result.message,
                "attempts": [
                    {
                        "strategy_id": attempt.strategy_id,
                        "status": attempt.status.value,
                        "elapsed_seconds": round(attempt.elapsed_seconds, 4),
                        "message": attempt.message,
                        "confidence": attempt.confidence,
                    }
                    for attempt in result.attempts
                ],
            }
        )

    def record_step_failure(self, workflow_id: str, step_id: str, message: str) -> tuple[int, bool]:
        key = f"failure:{workflow_id}:{step_id}"
        previous = self.state.get(self.namespace, key, {})
        previous = previous if isinstance(previous, dict) else {}
        same_failure = previous.get("last_message") == message
        count = int(previous.get("count", 0)) + 1 if same_failure else 1
        should_capture = count == self.diagnostic_failure_threshold
        self.state.set(
            self.namespace,
            key,
            {
                "count": count,
                "last_message": message,
                "last_failed_at": self.timing.clock.now().isoformat(),
            },
        )
        return count, should_capture

    def clear_step_failure(self, workflow_id: str, step_id: str) -> None:
        key = f"failure:{workflow_id}:{step_id}"
        previous = self.state.get(self.namespace, key, None)
        if previous is not None:
            self.state.set(
                self.namespace,
                key,
                {"count": 0, "cleared_at": self.timing.clock.now().isoformat()},
            )

    def diagnostic_metadata(
        self,
        workflow_id: str,
        step_id: str,
        message: str,
        failure_count: int,
    ) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "trace_id": self.trace_id,
            "cycle_id": self.cycle_id,
            "app_run_id": self.app_run_id,
            "step_run_id": self.step_run_id,
            "device_id": self.device_id,
            "app_id": self.app.app_id,
            "workflow_id": workflow_id,
            "step_id": step_id,
            "message": message,
            "consecutive_failure_count": failure_count,
            "recent_locator_attempts": list(self.recent_locator_attempts),
        }

    def emit(
        self,
        event_type: str,
        event_name: str,
        message: str,
        *,
        level: EventLevel = EventLevel.INFO,
        workflow_id: str | None = None,
        step_id: str | None = None,
        status: str | None = None,
        data: Mapping[str, Any] | None = None,
        artifacts: tuple[ArtifactRef, ...] = (),
    ) -> None:
        self.events.emit(
            AutomationEvent(
                event_type=event_type,
                event_name=event_name,
                trace_id=self.trace_id,
                device_id=self.device_id,
                cycle_id=self.cycle_id,
                app_run_id=self.app_run_id,
                step_run_id=self.step_run_id,
                level=level,
                message=message,
                app_id=self.app.app_id,
                workflow_id=workflow_id,
                step_id=step_id,
                status=status,
                data=data or {},
                artifacts=artifacts,
            )
        )

    def record_reward(
        self,
        reward_type: str,
        message: str,
        *,
        workflow_id: str,
        step_id: str,
        **data: Any,
    ) -> None:
        """记录已确认到账的奖励，不触发额外设备观察。"""

        self.emit(
            "reward.claim.confirmed",
            "奖励到账确认",
            message,
            workflow_id=workflow_id,
            step_id=step_id,
            status="success",
            data={"reward_type": reward_type, **data},
        )


_ACTION_STATUS_TEXT = {
    DailyActionStatus.NOT_STARTED: "未开始",
    DailyActionStatus.PENDING_CONFIRMATION: "已执行待确认",
    DailyActionStatus.CONFIRMED: "已确认",
    DailyActionStatus.UNCERTAIN: "结果不确定",
}
