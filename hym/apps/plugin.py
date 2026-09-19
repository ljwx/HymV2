from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from hym.apps.daily import DailyTaskSet, DailyWorkflowBuilder, ExtraStepFactory, TaskHandler
from hym.apps.specs import AppSpec, AudioContentSpec, NewsContentSpec, VideoContentSpec
from hym.core.models import WorkflowResult
from hym.runtime.audio import AudioContentTask, DefaultAudioPlayback
from hym.runtime.content import ContentTask
from hym.runtime.context import AppContext
from hym.runtime.navigation import NavigationController
from hym.runtime.news import NewsContentTask
from hym.runtime.rewards import (
    AdRewardTask,
    BalanceTask,
    CheckInTask,
    DurationRewardTask,
    WithdrawalTask,
)
from hym.runtime.video import VideoContentTask
from hym.runtime.workflow import StepOutcome, WorkflowDefinition, WorkflowExecutor


class WorkflowBuilder(Protocol):
    """插件只依赖工作流构建能力，不要求具体 App 继承公共父类。"""

    def build(self, context: AppContext) -> WorkflowDefinition: ...


@dataclass(frozen=True, slots=True)
class ComposedAppPlugin:
    """把 App 身份与工作流组合起来，本身不实现业务任务。"""

    spec: AppSpec
    workflow: WorkflowBuilder

    @property
    def app_id(self) -> str:
        return self.spec.identity.app_id

    def build_workflow(self, context: AppContext) -> WorkflowDefinition:
        return self.workflow.build(context)

    def run(self, context: AppContext) -> WorkflowResult:
        definition = self.build_workflow(context)
        return WorkflowExecutor().run(
            context,
            definition.workflow_id,
            definition.display_name,
            definition.steps,
        )


def create_daily_plugin(
    spec: AppSpec,
    *,
    navigation: NavigationController | None = None,
    task_page_navigator: Callable[[AppContext], bool] | None = None,
    content_handler: TaskHandler | None = None,
    tasks: DailyTaskSet | None = None,
    extra_steps: ExtraStepFactory | None = None,
    cleanup_steps: ExtraStepFactory | None = None,
) -> ComposedAppPlugin:
    """按需组合现有任务；特殊 App 可以替换单项任务或整个工作流。"""

    navigation = navigation or NavigationController(spec)
    if tasks is not None and (
        task_page_navigator is not None or content_handler is not None
    ):
        raise ValueError("显式 tasks 不能再同时传入单项任务覆盖")
    if tasks is None:
        tasks = create_daily_task_set(
            spec,
            navigation=navigation,
            task_page_navigator=task_page_navigator,
            content_handler=content_handler,
        )
    workflow = DailyWorkflowBuilder(
        spec=spec,
        navigation=navigation,
        tasks=tasks,
        extra_steps=extra_steps,
        cleanup_steps=cleanup_steps,
    )
    return ComposedAppPlugin(spec, workflow)


def create_daily_task_set(
    spec: AppSpec,
    *,
    navigation: NavigationController,
    task_page_navigator: Callable[[AppContext], bool] | None = None,
    content_handler: TaskHandler | None = None,
) -> DailyTaskSet:
    """生成可替换的默认任务集合，App 可用 dataclasses.replace 改其中一项。"""

    go_task_page = task_page_navigator or navigation.go_task_page
    content = content_handler
    if content is None and spec.content is not None:
        content = _create_content_handler(spec, navigation)
    return DailyTaskSet(
        content=ContentTask(content).run if content is not None else None,
        check_in=CheckInTask(spec, go_task_page).run if spec.check_in is not None else None,
        balance=BalanceTask(spec, go_task_page).run if spec.balance is not None else None,
        withdrawal=(
            WithdrawalTask(spec, go_task_page).run
            if spec.withdrawal is not None
            else None
        ),
        duration_reward=(
            DurationRewardTask(spec, go_task_page).run
            if spec.duration_reward is not None
            else None
        ),
        ad_reward=(
            AdRewardTask(spec, go_task_page, navigation.recover_home).run
            if spec.ad is not None and spec.ad_entry is not None
            else None
        ),
    )


def create_custom_plugin(spec: AppSpec, workflow: WorkflowBuilder) -> ComposedAppPlugin:
    """完全不同的 App 直接提供工作流，不经过默认奖励任务组合。"""

    return ComposedAppPlugin(spec, workflow)


def _create_content_handler(
    spec: AppSpec,
    navigation: NavigationController,
) -> TaskHandler:
    content = spec.content
    if isinstance(content, VideoContentSpec):
        return VideoContentTask(spec.identity, content, navigation).run
    if isinstance(content, NewsContentSpec):
        return NewsContentTask(content, navigation).run
    if isinstance(content, AudioContentSpec):
        return AudioContentTask(
            spec.identity,
            content,
            navigation,
            DefaultAudioPlayback(),
        ).run

    def unsupported(_: AppContext) -> StepOutcome:
        return StepOutcome.failure(
            f"没有注册内容策略: {spec.content_kind or '未知类型'}",
            retryable=False,
        )

    return unsupported
