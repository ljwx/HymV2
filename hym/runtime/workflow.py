from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
import traceback
from typing import Any, Mapping
from uuid import uuid4

from hym.core.events import EventLevel
from hym.core.control import TaskScope
from hym.core.models import ArtifactRef, StepResult, WorkflowResult, WorkflowStatus
from hym.runtime.context import AppContext
from hym.runtime.interruption import InterruptionRequest, WorkflowYield


@dataclass(frozen=True, slots=True)
class StepOutcome:
    status: WorkflowStatus
    message: str = ""
    outputs: Mapping[str, Any] = field(default_factory=dict)
    artifacts: tuple[ArtifactRef, ...] = ()

    @classmethod
    def success(cls, message: str = "", **outputs: Any) -> StepOutcome:
        return cls(WorkflowStatus.SUCCESS, message, outputs)

    @classmethod
    def skipped(cls, message: str = "") -> StepOutcome:
        return cls(WorkflowStatus.SKIPPED, message)

    @classmethod
    def failure(cls, message: str, *, retryable: bool = True) -> StepOutcome:
        status = WorkflowStatus.RETRYABLE_FAILURE if retryable else WorkflowStatus.FATAL
        return cls(status, message)


StepHandler = Callable[[AppContext], StepOutcome]
RecoveryHandler = Callable[[AppContext], None]


@dataclass(frozen=True, slots=True)
class StepDefinition:
    step_id: str
    display_name: str
    handler: StepHandler
    required: bool = False
    max_attempts: int = 1
    continue_on_failure: bool = True
    capture_on_failure: bool = True
    recovery: RecoveryHandler | None = None
    allow_interruption_after: bool = True
    task_scope: TaskScope = TaskScope.FULL_ONLY

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("步骤尝试次数必须大于零")


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    workflow_id: str
    display_name: str
    steps: tuple[StepDefinition, ...]

    def for_scope(self, scope: TaskScope) -> WorkflowDefinition:
        """保留启动/收尾步骤，只选择控制台要求的业务任务。"""

        if scope is TaskScope.FULL:
            return self
        business = tuple(step for step in self.steps if step.task_scope is scope)
        if not business:
            raise ValueError(f"当前应用不支持{scope.display_name}")
        selected = tuple(
            step
            for step in self.steps
            if step.task_scope in {TaskScope.SETUP, scope, TaskScope.CLEANUP}
        )
        return WorkflowDefinition(
            workflow_id=f"{self.workflow_id}:{scope.value}",
            display_name=f"{self.display_name}·{scope.display_name}",
            steps=selected,
        )


@dataclass(slots=True)
class WorkflowExecution:
    definition: WorkflowDefinition
    started_at: datetime | None = None
    next_index: int = 0
    results: list[StepResult] = field(default_factory=list)
    stopped: bool = False
    finished: bool = False

    @property
    def done(self) -> bool:
        return self.stopped or self.next_index >= len(self.definition.steps)

    @property
    def next_step_id(self) -> str | None:
        if self.done:
            return None
        return self.definition.steps[self.next_index].step_id


class WorkflowExecutor:
    """统一记录步骤链路、重试、诊断和最终状态。"""

    def run(
        self,
        context: AppContext,
        workflow_id: str,
        display_name: str,
        steps: Sequence[StepDefinition],
    ) -> WorkflowResult:
        execution = self.create(workflow_id, display_name, steps)
        while not execution.done:
            self.run_next(context, execution)
        return self.finish(context, execution)

    def create(
        self,
        workflow_id: str,
        display_name: str,
        steps: Sequence[StepDefinition],
    ) -> WorkflowExecution:
        return WorkflowExecution(
            WorkflowDefinition(workflow_id, display_name, tuple(steps)),
        )

    def run_next(
        self,
        context: AppContext,
        execution: WorkflowExecution,
    ) -> StepResult | None:
        if execution.finished:
            raise RuntimeError("工作流已经结束")
        self._ensure_started(context, execution)
        if execution.done:
            return None
        definition = execution.definition.steps[execution.next_index]
        result = self._run_step(context, execution.definition.workflow_id, definition)
        execution.results.append(result)
        execution.next_index += 1
        failed = result.status in {
            WorkflowStatus.RETRYABLE_FAILURE,
            WorkflowStatus.NO_PROGRESS,
            WorkflowStatus.FATAL,
        }
        if failed and definition.required and not definition.continue_on_failure:
            execution.stopped = True
        self._save_cursor(context, execution, "running")
        return result

    def suspend(
        self,
        context: AppContext,
        execution: WorkflowExecution,
        request: InterruptionRequest,
    ) -> None:
        self._ensure_started(context, execution)
        context.emit(
            "workflow.suspended",
            "工作流暂停",
            f"在安全点暂停{execution.definition.display_name}",
            workflow_id=execution.definition.workflow_id,
            step_id=execution.next_step_id,
            status="suspended",
            data={"checkpoint": request.checkpoint, **request.data},
        )
        self._save_cursor(context, execution, "suspended")

    def resume(self, context: AppContext, execution: WorkflowExecution) -> None:
        context.emit(
            "workflow.resumed",
            "工作流恢复",
            f"继续执行{execution.definition.display_name}",
            workflow_id=execution.definition.workflow_id,
            step_id=execution.next_step_id,
            status="running",
            data={"next_index": execution.next_index},
        )
        self._save_cursor(context, execution, "running")

    def finish(
        self,
        context: AppContext,
        execution: WorkflowExecution,
    ) -> WorkflowResult:
        if execution.finished:
            raise RuntimeError("工作流已经结束")
        self._ensure_started(context, execution)
        if not execution.done:
            raise RuntimeError("工作流仍有未执行步骤")
        status = _workflow_status(execution.results)
        finished = context.timing.clock.now()
        execution.finished = True
        definition = execution.definition
        context.emit(
            "workflow.finished",
            "工作流结束",
            f"{definition.display_name}执行结束",
            workflow_id=definition.workflow_id,
            status=status.value,
            data={
                "step_count": len(execution.results),
                "duration_ms": max(0, int((finished - (execution.started_at or finished)).total_seconds() * 1000)),
            },
        )
        self._save_cursor(context, execution, "completed")
        return WorkflowResult(
            definition.workflow_id,
            status,
            execution.started_at or finished,
            finished,
            tuple(execution.results),
        )

    def _ensure_started(self, context: AppContext, execution: WorkflowExecution) -> None:
        if execution.started_at is not None:
            return
        execution.started_at = context.timing.clock.now()
        definition = execution.definition
        context.emit(
            "workflow.started",
            "工作流开始",
            f"开始执行{definition.display_name}",
            workflow_id=definition.workflow_id,
            status="started",
        )
        self._save_cursor(context, execution, "running")

    @staticmethod
    def _save_cursor(
        context: AppContext,
        execution: WorkflowExecution,
        status: str,
    ) -> None:
        context.state.set(
            context.namespace,
            "runtime:workflow_cursor",
            {
                "cycle_id": context.cycle_id,
                "workflow_id": execution.definition.workflow_id,
                "status": status,
                "step_ids": [item.step_id for item in execution.definition.steps],
                "next_index": execution.next_index,
                "next_step_id": execution.next_step_id,
                "updated_at": context.timing.clock.now().isoformat(),
            },
        )

    def _run_step(
        self,
        context: AppContext,
        workflow_id: str,
        definition: StepDefinition,
    ) -> StepResult:
        started = context.timing.clock.now()
        outcome = StepOutcome.failure("步骤尚未执行")
        attempts = 0

        for attempts in range(1, definition.max_attempts + 1):
            context.step_run_id = uuid4().hex
            context.emit(
                "step.started",
                "步骤开始",
                f"开始执行{definition.display_name}",
                workflow_id=workflow_id,
                step_id=definition.step_id,
                status="started",
                data={"attempt": attempts},
            )
            try:
                outcome = definition.handler(context)
            except WorkflowYield as interruption:
                context.emit(
                    "step.suspended",
                    "步骤安全暂停",
                    f"{definition.display_name}在安全点暂停",
                    workflow_id=workflow_id,
                    step_id=definition.step_id,
                    status="suspended",
                    data={
                        "checkpoint": interruption.request.checkpoint,
                        **interruption.request.data,
                    },
                )
                context.step_run_id = None
                raise
            except Exception as error:
                outcome = StepOutcome(
                    WorkflowStatus.RETRYABLE_FAILURE,
                    f"步骤发生异常: {error}",
                    {
                        "exception_type": type(error).__name__,
                        "traceback": traceback.format_exc(),
                    },
                )

            if outcome.status not in {WorkflowStatus.RETRYABLE_FAILURE, WorkflowStatus.NO_PROGRESS}:
                break
            if attempts < definition.max_attempts:
                context.emit(
                    "step.retrying",
                    "步骤准备重试",
                    f"{definition.display_name}未完成，准备重试",
                    level=EventLevel.WARNING,
                    workflow_id=workflow_id,
                    step_id=definition.step_id,
                    status=outcome.status.value,
                    data={"attempt": attempts},
                )
                if definition.recovery is not None:
                    definition.recovery(context)

        failed = outcome.status in {
            WorkflowStatus.RETRYABLE_FAILURE,
            WorkflowStatus.NO_PROGRESS,
            WorkflowStatus.FATAL,
        }
        artifacts = outcome.artifacts
        failure_count = 0
        if failed:
            failure_count, threshold_reached = context.record_step_failure(
                workflow_id,
                definition.step_id,
                outcome.message,
            )
            should_capture = definition.capture_on_failure and (
                threshold_reached or outcome.status is WorkflowStatus.FATAL
            )
            if should_capture:
                context.emit(
                    "diagnostic.threshold.reached",
                    "诊断采集触发",
                    f"{definition.display_name}已连续失败 {failure_count} 次，开始保存现场",
                    level=EventLevel.WARNING,
                    workflow_id=workflow_id,
                    step_id=definition.step_id,
                    status="failed",
                    data={"consecutive_failure_count": failure_count},
                )
                artifacts += context.diagnostics.capture(
                    f"{context.app.app_id}-{workflow_id}-{definition.step_id}",
                    metadata=context.diagnostic_metadata(
                        workflow_id,
                        definition.step_id,
                        outcome.message,
                        failure_count,
                    ),
                )
        else:
            context.clear_step_failure(workflow_id, definition.step_id)
        if failed and definition.recovery is not None:
            try:
                definition.recovery(context)
            except Exception as error:
                context.emit(
                    "step.recovery.failed",
                    "步骤恢复失败",
                    f"{definition.display_name}恢复失败: {error}",
                    level=EventLevel.WARNING,
                    workflow_id=workflow_id,
                    step_id=definition.step_id,
                    status="failed",
                )

        finished = context.timing.clock.now()
        level = (
            EventLevel.INFO
            if outcome.status
            in {WorkflowStatus.SUCCESS, WorkflowStatus.ALREADY_DONE, WorkflowStatus.SKIPPED}
            else EventLevel.WARNING
        )
        context.emit(
            "step.finished",
            "步骤结束",
            outcome.message or f"{definition.display_name}执行结束",
            level=level,
            workflow_id=workflow_id,
            step_id=definition.step_id,
            status=outcome.status.value,
            data={
                "attempts": attempts,
                "consecutive_failure_count": failure_count,
                "duration_ms": max(0, int((finished - started).total_seconds() * 1000)),
                **outcome.outputs,
            },
            artifacts=artifacts,
        )
        result = StepResult(
            step_id=definition.step_id,
            status=outcome.status,
            started_at=started,
            finished_at=finished,
            attempts=attempts,
            message=outcome.message,
            outputs=outcome.outputs,
            artifacts=artifacts,
        )
        context.step_run_id = None
        return result


def _workflow_status(results: Sequence[StepResult]) -> WorkflowStatus:
    if not results:
        return WorkflowStatus.SKIPPED
    statuses = {result.status for result in results}
    if WorkflowStatus.FATAL in statuses:
        return WorkflowStatus.FATAL
    if WorkflowStatus.PARTIAL in statuses:
        return WorkflowStatus.PARTIAL
    failures = statuses & {WorkflowStatus.RETRYABLE_FAILURE, WorkflowStatus.NO_PROGRESS}
    successes = statuses & {WorkflowStatus.SUCCESS, WorkflowStatus.ALREADY_DONE}
    if failures and successes:
        return WorkflowStatus.PARTIAL
    if WorkflowStatus.NO_PROGRESS in statuses:
        return WorkflowStatus.NO_PROGRESS
    if WorkflowStatus.RETRYABLE_FAILURE in statuses:
        return WorkflowStatus.RETRYABLE_FAILURE
    if statuses <= {WorkflowStatus.SKIPPED}:
        return WorkflowStatus.SKIPPED
    return WorkflowStatus.SUCCESS
