from __future__ import annotations

import traceback
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

from hym.adapters.airtest_poco import AirtestPocoDeviceFactory
from hym.adapters.local import AtomicJsonStateStore, LocalArtifactStore, SystemClock, SystemRandomSource
from hym.adapters.reporting import DurableHttpEventSink
from hym.apps.registry import AppPlugin, AppRegistry, create_default_registry
from hym.core.config import AppRunSettings, DeviceRunSettings, RuntimeSettings, load_runtime_settings
from hym.core.events import (
    AutomationEvent,
    CompositeEventSink,
    ConsoleEventSink,
    EventFilter,
    EventLevel,
    JsonlEventSink,
)
from hym.core.models import SystemKey
from hym.core.models import WorkflowStatus
from hym.core.pages import ObservationProfile
from hym.core.ports import DeviceFactoryPort, LocatorPort
from hym.core.randomness import bounded_normal
from hym.locators.hybrid import HybridLocator
from hym.locators.vision import OpenCvTemplateMatcher, create_ocr_engine
from hym.runtime.actions import ActionController
from hym.runtime.behavior import BehaviorTiming
from hym.runtime.context import AppContext
from hym.runtime.diagnostics import DiagnosticsService
from hym.runtime.interruption import (
    InterruptionKind,
    InterruptionPolicy,
    InterruptionRequest,
    WorkflowYield,
)
from hym.runtime.lease import DeviceBusyError, DeviceLease
from hym.runtime.schedule import DailyAppScheduler
from hym.runtime.session import DeviceSession
from hym.runtime.workflow import WorkflowExecution, WorkflowExecutor


def run_device_from_config(
    config_path: str | Path,
    device_id: str,
    once: bool,
    app_ids: Iterable[str] | None = None,
) -> int:
    settings = load_runtime_settings(config_path)
    device = next((item for item in settings.devices if item.descriptor.device_id == device_id), None)
    if device is None:
        raise ValueError(f"配置中没有设备: {device_id}")
    selected = set(app_ids or ())
    if selected:
        apps = tuple(app for app in device.apps if app.enabled and app.app_id in selected)
        if not apps:
            names = "、".join(sorted(selected))
            raise ValueError(f"设备 {device_id} 没有匹配到已启用 App: {names}")
        device = replace(device, apps=apps)
    registry = create_default_registry()
    if any(app.app_id == "wechat" for app in device.apps):
        from wechat_automation.config import WechatSettings, load_wechat_settings
        from wechat_automation.plugin import WechatPlugin

        runtime_path = Path(config_path).resolve()
        wechat_path = runtime_path.with_name("wechat.local.json")
        wechat_settings = (
            load_wechat_settings(wechat_path)
            if wechat_path.exists()
            else WechatSettings(runtime_config=runtime_path)
        )
        registry.register(WechatPlugin(wechat_settings))
    return DeviceWorker(settings, device, registry).run(once=once)


@dataclass(slots=True)
class _AppJob:
    settings: AppRunSettings
    plugin: AppPlugin
    context: AppContext
    execution: WorkflowExecution
    started: bool = False
    suspended: bool = False
    completed: bool = False


class DeviceWorker:
    """单设备执行可恢复 App 切片；多设备仍通过进程隔离并行。"""

    def __init__(
        self,
        settings: RuntimeSettings,
        device: DeviceRunSettings,
        registry: AppRegistry,
        *,
        device_factory: DeviceFactoryPort | None = None,
        locator: LocatorPort | None = None,
    ) -> None:
        self.settings = settings
        self.device_settings = device
        self.registry = registry
        self.clock = SystemClock()
        self.random = SystemRandomSource()
        self.events = self._create_events()
        self.session = DeviceSession(
            device.descriptor,
            device_factory or AirtestPocoDeviceFactory(),
            self.events,
            self.clock,
            settings.retry,
        )
        self.state = AtomicJsonStateStore(settings.state_dir / f"{_safe_id(device.descriptor.device_id)}.json")
        self.artifacts = LocalArtifactStore(settings.artifact_dir / _safe_id(device.descriptor.device_id))
        self.scheduler = DailyAppScheduler(
            device.descriptor.device_id,
            self.state,
            self.clock,
            self.random,
        )
        image_matcher = OpenCvTemplateMatcher(settings.resource_dir) if settings.vision.enable_image_matching else None
        self.ocr = (
            create_ocr_engine(settings.vision.ocr_engine, settings.vision.ocr_language)
            if settings.vision.enable_ocr
            else None
        )
        self.locator = locator or HybridLocator(
            self.random,
            ocr_engine=self.ocr,
            image_matcher=image_matcher,
        )
        self.lease = DeviceLease(
            settings.state_dir / ".locks" / f"{_safe_id(device.descriptor.device_id)}.lock"
        )

    def run(self, *, once: bool) -> int:
        try:
            with self.lease:
                if not self.session.connect():
                    return 2
                try:
                    while True:
                        self._run_cycle()
                        if once:
                            return 0
                        self.clock.sleep(self.settings.loop_interval_seconds)
                finally:
                    self.session.close()
        except DeviceBusyError as error:
            trace_id = uuid4().hex
            self._emit_worker_event(
                trace_id,
                "runtime.device.busy",
                "设备任务冲突",
                str(error),
                level=EventLevel.ERROR,
                status="failed",
            )
            return 3

    def _run_cycle(self) -> None:
        trace_id = uuid4().hex
        self._cycle_business_date = self.clock.now().astimezone().date()
        self._emit_worker_event(
            trace_id,
            "runtime.cycle.started",
            "执行轮次开始",
            "开始新一轮设备任务",
            status="started",
        )
        executor = WorkflowExecutor()
        interruption_policy = InterruptionPolicy(
            self.settings.interruptions,
            self.clock,
            self.random,
        )
        jobs: list[_AppJob] = []
        issue_count = 0
        successful_app_count = 0
        for app_settings in self.device_settings.apps:
            if not app_settings.enabled:
                continue
            scheduler = getattr(self, "scheduler", None)
            if scheduler is not None and not scheduler.is_due(app_settings.app_id, app_settings.options):
                continue
            plugin = self.registry.get(app_settings.app_id)
            if plugin is None:
                self._emit_worker_event(
                    trace_id,
                    "app.plugin.missing",
                    "应用插件缺失",
                    f"没有注册应用插件: {app_settings.app_id}",
                    level=EventLevel.ERROR,
                    status="failed",
                    app_id=app_settings.app_id,
                )
                issue_count += 1
                continue
            context = self._create_context(trace_id, app_settings, plugin)
            if bool(context.option("allow_interruptions", True)):
                context.safe_point_handler = interruption_policy.yield_if_requested
            definition = plugin.build_workflow(context)
            jobs.append(
                _AppJob(
                    app_settings,
                    plugin,
                    context,
                    executor.create(
                        definition.workflow_id,
                        definition.display_name,
                        definition.steps,
                    ),
                )
            )

        current_index = self._next_pending_index(jobs, -1)
        while current_index is not None:
            job = jobs[current_index]
            context = job.context
            if not job.started:
                job.started = True
                scheduler = getattr(self, "scheduler", None)
                if scheduler is not None:
                    scheduler.mark_started(job.settings.app_id, job.settings.options)
                context.emit(
                    "app.started",
                    "应用任务开始",
                    f"开始执行{job.plugin.spec.display_name}",
                    status="started",
                    data={"business_date": context.business_date.isoformat()},
                )
            elif job.suspended:
                executor.resume(context, job.execution)
                job.suspended = False

            try:
                result = executor.run_next(context, job.execution)
            except WorkflowYield as interruption:
                executor.suspend(context, job.execution, interruption.request)
                job.suspended = True
                current_index = self._handle_interruption(
                    jobs,
                    current_index,
                    interruption.request,
                )
                continue
            except Exception as error:
                self._record_unhandled_app_error(job, error)
                issue_count += 1
                job.completed = True
                self._finish_app(context, job.plugin.spec.identity)
                current_index = self._next_pending_index(jobs, current_index)
                continue

            if job.execution.done:
                workflow_result = executor.finish(context, job.execution)
                context.emit(
                    "app.finished",
                    "应用任务结束",
                    f"{job.plugin.spec.display_name}本轮执行结束",
                    status=workflow_result.status.value,
                    data={"workflow_id": workflow_result.workflow_id},
                )
                if workflow_result.status in {
                    WorkflowStatus.SUCCESS,
                    WorkflowStatus.ALREADY_DONE,
                    WorkflowStatus.SKIPPED,
                }:
                    successful_app_count += 1
                else:
                    issue_count += 1
                job.completed = True
                self._finish_app(context, job.plugin.spec.identity)
                current_index = self._next_pending_index(jobs, current_index)
                continue

            definition = job.execution.definition.steps[job.execution.next_index - 1]
            request = None
            if (
                result is not None
                and definition.allow_interruption_after
                and bool(context.option("allow_interruptions", True))
            ):
                request = interruption_policy.request(
                    "step.finished",
                    {
                        "step_id": result.step_id,
                        "next_step_id": job.execution.next_step_id,
                    },
                )
            if request is not None:
                executor.suspend(context, job.execution, request)
                job.suspended = True
                current_index = self._handle_interruption(jobs, current_index, request)
        cycle_status = "success"
        cycle_level = EventLevel.INFO
        if issue_count:
            cycle_status = "partial" if successful_app_count else "failed"
            cycle_level = EventLevel.WARNING if successful_app_count else EventLevel.ERROR
        self._emit_worker_event(
            trace_id,
            "runtime.cycle.finished",
            "执行轮次结束",
            f"本轮设备任务执行结束，完整完成 {successful_app_count} 个应用，异常 {issue_count} 处",
            level=cycle_level,
            status=cycle_status,
        )

    def _create_context(
        self,
        trace_id: str,
        app_settings: AppRunSettings,
        plugin: AppPlugin,
    ) -> AppContext:
        behavior = self.settings.behavior_for(self.device_settings, app_settings)
        timing = BehaviorTiming(behavior, self.clock, self.random)
        diagnostics = DiagnosticsService(self.session, self.artifacts)
        context = AppContext(
            app=plugin.spec.identity,
            settings=app_settings,
            session=self.session,
            timing=timing,
            random_source=self.random,
            state=self.state,
            events=self.events,
            diagnostics=diagnostics,
            diagnostic_failure_threshold=self.settings.diagnostics.consecutive_failure_threshold,
            diagnostic_capture_interval=self.settings.diagnostics.capture_every_failures,
            cycle_id=trace_id,
            app_run_id=uuid4().hex,
            business_date=getattr(self, "_cycle_business_date", None),
            observation_profile=getattr(
                plugin.spec,
                "observation_profile",
                ObservationProfile(),
            ),
            ocr=self.ocr,
        )
        context.actions = ActionController(context, self.locator)
        return context

    def _handle_interruption(
        self,
        jobs: list[_AppJob],
        current_index: int,
        request: InterruptionRequest,
    ) -> int:
        job = jobs[current_index]
        context = job.context
        candidates = [
            index
            for index, candidate in enumerate(jobs)
            if index != current_index and not candidate.completed
        ]
        if request.kind is InterruptionKind.APP_SWITCH and candidates:
            target_index = self.random.choice(candidates)
            target = jobs[target_index]
            context.emit(
                "runtime.interruption.app_switch",
                "随机切换应用",
                f"暂停{job.plugin.spec.display_name}，切换到{target.plugin.spec.display_name}",
                workflow_id=job.execution.definition.workflow_id,
                step_id=job.execution.next_step_id,
                status="suspended",
                data={
                    "checkpoint": request.checkpoint,
                    "from_app_id": job.plugin.app_id,
                    "to_app_id": target.plugin.app_id,
                    "next_step_id": job.execution.next_step_id,
                },
            )
            return target_index

        wait_seconds = bounded_normal(
            self.random,
            self.settings.interruptions.desktop_wait_seconds_min,
            self.settings.interruptions.desktop_wait_seconds_max,
            center=self.settings.interruptions.desktop_wait_seconds_center,
            stddev=self.settings.interruptions.desktop_wait_seconds_stddev,
        )
        context.emit(
            "runtime.interruption.desktop.started",
            "随机返回桌面",
            f"返回桌面停留约 {wait_seconds:.1f} 秒",
            workflow_id=job.execution.definition.workflow_id,
            step_id=job.execution.next_step_id,
            status="waiting",
            data={
                "checkpoint": request.checkpoint,
                "wait_seconds": round(wait_seconds, 2),
                "next_step_id": job.execution.next_step_id,
            },
        )
        context.actions.press(SystemKey.HOME)
        self.clock.sleep(wait_seconds)
        context.emit(
            "runtime.interruption.desktop.finished",
            "桌面停留结束",
            "桌面随机停留结束，准备恢复任务",
            workflow_id=job.execution.definition.workflow_id,
            step_id=job.execution.next_step_id,
            status="success",
            data={"wait_seconds": round(wait_seconds, 2)},
        )
        return current_index

    @staticmethod
    def _next_pending_index(jobs: list[_AppJob], current_index: int) -> int | None:
        for offset in range(1, len(jobs) + 1):
            index = (current_index + offset) % len(jobs)
            if not jobs[index].completed:
                return index
        return None

    def _record_unhandled_app_error(self, job: _AppJob, error: Exception) -> None:
        context = job.context
        artifacts = context.diagnostics.capture(
            f"{job.plugin.app_id}-unhandled",
            metadata={
                "schema_version": "1.0",
                "trace_id": context.trace_id,
                "device_id": context.device_id,
                "app_id": context.app.app_id,
                "message": str(error),
                "traceback": traceback.format_exc(),
                "recent_locator_attempts": list(context.recent_locator_attempts),
            },
        )
        context.emit(
            "app.failed",
            "应用任务异常",
            f"{job.plugin.spec.display_name}发生未处理异常: {error}",
            level=EventLevel.ERROR,
            status="failed",
            data={"traceback": traceback.format_exc()},
            artifacts=artifacts,
        )

    def _finish_app(self, context: AppContext, app) -> None:
        stop_probability = float(context.option("stop_app_probability", 0.5))
        if context.random.random() >= stop_probability:
            return
        context.actions.press(SystemKey.HOME)
        context.timing.operation_delay()
        context.session.stop_app(app)

    def _create_events(self):
        device_id = _safe_id(self.device_settings.descriptor.device_id)
        sinks = [
            ConsoleEventSink(
                EventFilter(min_level=EventLevel(self.settings.logging.console_level))
            ),
        ]
        if self.settings.logging.write_jsonl:
            sinks.append(
                JsonlEventSink(
                    self.settings.log_dir / f"{device_id}.jsonl",
                    EventFilter(min_level=EventLevel(self.settings.logging.jsonl_level)),
                )
            )
        if self.settings.reporting.enabled:
            apps = tuple(
                plugin.spec.identity
                for app_id in self.registry.app_ids()
                if (plugin := self.registry.get(app_id)) is not None
            )
            sinks.append(
                DurableHttpEventSink(
                    self.settings.reporting,
                    self.settings.report_queue_dir / f"{device_id}.jsonl",
                    self.device_settings.descriptor,
                    apps,
                    event_filter=EventFilter(
                        min_level=EventLevel(self.settings.reporting.level)
                    ),
                )
            )
        return CompositeEventSink(sinks)

    def _emit_worker_event(
        self,
        trace_id: str,
        event_type: str,
        event_name: str,
        message: str,
        *,
        level: EventLevel = EventLevel.INFO,
        status: str | None = None,
        app_id: str | None = None,
    ) -> None:
        self.events.emit(
            AutomationEvent(
                event_type=event_type,
                event_name=event_name,
                trace_id=trace_id,
                device_id=self.device_settings.descriptor.device_id,
                cycle_id=trace_id,
                level=level,
                status=status,
                message=message,
                app_id=app_id,
            )
        )


def _safe_id(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_." else "_" for char in value)
