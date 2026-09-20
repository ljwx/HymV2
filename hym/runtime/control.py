from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping
from uuid import uuid4

from hym.core.control import DeviceControlState, RemoteCommand, TaskScope
from hym.core.events import EventLevel
from hym.core.models import SystemKey
from hym.core.ports import ClockPort, RemoteControlPort
from hym.runtime.context import AppContext
from hym.runtime.interruption import InterruptionKind, InterruptionPolicy, InterruptionRequest, WorkflowYield


@dataclass(slots=True)
class RemoteControlCoordinator:
    """低频访问控制服务；失败后退避，不把网络状态变成设备任务阻塞点。"""

    port: RemoteControlPort
    device_id: str
    clock: ClockPort
    poll_interval_seconds: float
    retry_interval_seconds: float
    _next_pause_poll_at: float = 0.0
    _next_command_poll_at: float = 0.0
    _last_error: str = ""
    _last_reported_state: str = ""
    _last_control_state: DeviceControlState | None = None

    def poll_control(self, *, force: bool = False) -> DeviceControlState | None:
        now = self._now_seconds()
        if not force and now < self._next_pause_poll_at:
            return self._last_control_state
        try:
            state = self.port.control(self.device_id)
        except Exception as error:
            self._remember_error(error)
            self._next_pause_poll_at = now + self.retry_interval_seconds
            return None
        self._next_pause_poll_at = now + self.poll_interval_seconds
        self._last_control_state = state
        return state

    def poll_pause(self, *, force: bool = False) -> DeviceControlState | None:
        state = self.poll_control(force=force)
        return state if state is not None and (state.pause_requested or state.desired_state == "paused") else None

    def report_state(self, state: str, *, force: bool = False) -> bool:
        if not force and state == self._last_reported_state:
            return True
        try:
            self.port.report_state(self.device_id, state)
        except Exception as error:
            self._remember_error(error)
            return False
        self._last_reported_state = state
        return True

    def wait_for_resume(self, initial: DeviceControlState) -> str:
        now_ms = self._now_millis()
        deadline_ms = min(
            initial.pause_until_ms or now_ms + MAX_PAUSE_MS,
            now_ms + MAX_PAUSE_MS,
        )
        try:
            self.port.acknowledge_pause(self.device_id)
        except Exception as error:
            self._remember_error(error)
        self.report_state("paused", force=True)

        while self._now_millis() < deadline_ms:
            remaining = max(0.0, (deadline_ms - self._now_millis()) / 1_000)
            self.clock.sleep(min(self.poll_interval_seconds, remaining))
            try:
                state = self.port.control(self.device_id)
            except Exception as error:
                self._remember_error(error)
                continue
            if not state.pause_requested and state.desired_state != "paused":
                self._next_pause_poll_at = self._now_seconds() + self.poll_interval_seconds
                return "manual"
            if state.pause_until_ms is not None:
                deadline_ms = min(deadline_ms, state.pause_until_ms)
        self._next_pause_poll_at = self._now_seconds() + self.poll_interval_seconds
        return "timeout"

    def claim_command(self, *, force: bool = False) -> RemoteCommand | None:
        now = self._now_seconds()
        if not force and now < self._next_command_poll_at:
            return None
        try:
            command = self.port.claim_command(self.device_id)
        except Exception as error:
            self._remember_error(error)
            self._next_command_poll_at = now + self.retry_interval_seconds
            return None
        self._next_command_poll_at = now + self.poll_interval_seconds
        return command

    def complete_command(self, command: RemoteCommand, *, succeeded: bool, message: str) -> bool:
        try:
            self.port.complete_command(
                self.device_id,
                command.command_id,
                succeeded=succeeded,
                message=message,
            )
        except Exception as error:
            self._remember_error(error)
            return False
        return True

    def take_error(self) -> str:
        error, self._last_error = self._last_error, ""
        return error

    def _remember_error(self, error: Exception) -> None:
        if not self._last_error:
            self._last_error = str(error)

    def _now_seconds(self) -> float:
        return self.clock.now().timestamp()

    def _now_millis(self) -> int:
        return int(self._now_seconds() * 1_000)


MAX_PAUSE_MS = 45 * 60 * 1_000


class DeviceControlRuntime:
    """把远程控制转换为运行器可使用的安全暂停和任务命令。"""

    def __init__(
        self,
        coordinator: RemoteControlCoordinator,
        emit_worker: Callable[..., None],
    ) -> None:
        self.coordinator = coordinator
        self.emit_worker = emit_worker

    def poll_pause(self) -> DeviceControlState | None:
        state = self.coordinator.poll_pause()
        self.emit_error(uuid4().hex)
        return state

    def poll_control(self, *, force: bool = False) -> DeviceControlState | None:
        state = self.coordinator.poll_control(force=force)
        self.emit_error(uuid4().hex)
        return state

    def report_state(self, state: str, *, force: bool = False) -> None:
        self.coordinator.report_state(state, force=force)
        self.emit_error(uuid4().hex)

    def claim_command(self) -> RemoteCommand | None:
        command = self.coordinator.claim_command()
        self.emit_error(uuid4().hex)
        return command

    def run_command(
        self,
        command: RemoteCommand,
        *,
        session: Any,
        run_cycle: Callable[..., str],
        loop_interval_seconds: float,
    ) -> None:
        if command.scope in {TaskScope.DEVICE_VOLUME, TaskScope.SCREEN_BRIGHTNESS}:
            self._run_device_setting(command, session)
            return
        if command.scope in {TaskScope.DEVICE_HOME, TaskScope.DEVICE_LOCK, TaskScope.DEVICE_UNLOCK}:
            self._run_device_action(command, session)
            return
        statuses: list[str] = []
        message = ""
        app_ids = {command.app_id} if command.app_id else None
        for round_index in range(command.rounds):
            if not session.connect():
                message = "设备连接失败"
                statuses.append("failed")
                break
            try:
                status = run_cycle(
                    app_ids=app_ids,
                    task_scope=command.scope,
                    force=True,
                    sequential=True,
                )
                statuses.append(status)
            except Exception as error:
                message = str(error)
                statuses.append("failed")
                break
            finally:
                session.close()
            if statuses[-1] == "cancelled":
                message = "任务已按停止指令终止"
                break
            if round_index < command.rounds - 1:
                self.coordinator.clock.sleep(loop_interval_seconds)

        succeeded = bool(statuses) and all(status == "success" for status in statuses)
        if not message:
            completed = sum(status == "success" for status in statuses)
            message = f"已完成 {completed}/{command.rounds} 轮"
        self.coordinator.complete_command(command, succeeded=succeeded, message=message)
        self.emit_error(uuid4().hex)

    def _run_device_action(self, command: RemoteCommand, session: Any) -> None:
        if not session.connect():
            self.coordinator.complete_command(command, succeeded=False, message="设备连接失败")
            return
        try:
            if command.scope is TaskScope.DEVICE_HOME:
                result, message = session.press(SystemKey.HOME), "已返回桌面"
            elif command.scope is TaskScope.DEVICE_LOCK:
                result, message = session.press(SystemKey.SLEEP), "手机已锁屏"
            else:
                result, message = session.unlock(), "手机已解锁"
        except Exception as error:
            self.coordinator.complete_command(command, succeeded=False, message=str(error))
            return
        finally:
            session.close()
        self.coordinator.complete_command(
            command,
            succeeded=result.succeeded,
            message=message if result.succeeded else result.message,
        )
        self.emit_error(uuid4().hex)

    def _run_device_setting(self, command: RemoteCommand, session: Any) -> None:
        value = command.value
        if value is None or not 0 <= value <= 100:
            self.coordinator.complete_command(
                command,
                succeeded=False,
                message="设备设置值必须位于 0 到 100 之间",
            )
            return
        if not session.connect():
            self.coordinator.complete_command(command, succeeded=False, message="设备连接失败")
            return
        try:
            try:
                result = (
                    session.set_media_volume(value)
                    if command.scope is TaskScope.DEVICE_VOLUME
                    else session.set_screen_brightness(value)
                )
            except Exception as error:
                self.coordinator.complete_command(
                    command,
                    succeeded=False,
                    message=str(error),
                )
                return
        finally:
            session.close()
        label = "媒体音量" if command.scope is TaskScope.DEVICE_VOLUME else "屏幕亮度"
        self.coordinator.complete_command(
            command,
            succeeded=result.succeeded,
            message=(f"{label}已设置为 {value}%" if result.succeeded else result.message),
        )
        self.emit_error(uuid4().hex)

    def yield_at_safe_point(
        self,
        context: AppContext,
        interruption_policy: InterruptionPolicy,
        checkpoint: str,
        data: Mapping[str, Any],
        *,
        allow_random: bool,
    ) -> None:
        pause = self.pause_request(checkpoint, data, context=context)
        if pause is not None:
            raise WorkflowYield(pause)
        if allow_random:
            interruption_policy.yield_if_requested(checkpoint, data)

    def pause_request(
        self,
        checkpoint: str,
        data: Mapping[str, Any],
        *,
        context: AppContext | None = None,
    ) -> InterruptionRequest | None:
        state = self.coordinator.poll_control()
        self.emit_error(context.trace_id if context is not None else uuid4().hex, context=context)
        if state is None or state.desired_state == "running":
            return None
        return InterruptionRequest(
            InterruptionKind.USER_STOP if state.desired_state == "stopped" else InterruptionKind.USER_PAUSE,
            checkpoint,
            {
                **dict(data),
                "requested_at_ms": state.requested_at_ms,
                "pause_until_ms": state.pause_until_ms,
            },
        )

    def wait(
        self,
        state: DeviceControlState,
        *,
        trace_id: str | None = None,
        context: AppContext | None = None,
    ) -> None:
        if context is not None:
            context.actions.press(SystemKey.HOME)
            context.emit(
                "runtime.control.pause.started",
                "设备暂停",
                "当前任务已到安全点，返回桌面等待继续",
                status="waiting",
                data={"pause_until_ms": state.pause_until_ms},
            )
        else:
            self.emit_worker(
                trace_id or uuid4().hex,
                "runtime.control.pause.started",
                "设备暂停",
                "设备当前没有执行任务，等待继续",
                status="waiting",
            )
        reason = self.coordinator.wait_for_resume(state)
        self.coordinator.report_state("running", force=True)
        message = "收到继续指令，恢复执行" if reason == "manual" else "暂停达到 45 分钟，自动恢复执行"
        if context is not None:
            context.emit(
                "runtime.control.pause.finished",
                "设备继续",
                message,
                status="success",
                data={"resume_reason": reason},
            )
        else:
            self.emit_worker(
                trace_id or uuid4().hex,
                "runtime.control.pause.finished",
                "设备继续",
                message,
                status="success",
            )
        self.emit_error(
            context.trace_id if context is not None else trace_id or uuid4().hex,
            context=context,
        )

    def state_from(self, request: InterruptionRequest) -> DeviceControlState:
        return DeviceControlState(
            device_id=self.coordinator.device_id,
            pause_requested=True,
            requested_at_ms=request.data.get("requested_at_ms"),
            pause_until_ms=request.data.get("pause_until_ms"),
        )

    def emit_error(self, trace_id: str, *, context: AppContext | None = None) -> None:
        message = self.coordinator.take_error()
        if not message:
            return
        if context is not None:
            context.emit(
                "runtime.control.unavailable",
                "运行控制暂不可用",
                message,
                level=EventLevel.WARNING,
                status="unavailable",
            )
        else:
            self.emit_worker(
                trace_id,
                "runtime.control.unavailable",
                "运行控制暂不可用",
                message,
                level=EventLevel.WARNING,
                status="unavailable",
            )
