from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from hym.apps.specs import AppSpec
from hym.runtime.context import AppContext
from hym.runtime.navigation import NavigationController
from hym.runtime.workflow import StepDefinition, StepOutcome, WorkflowDefinition


TaskHandler = Callable[[AppContext], StepOutcome]
ExtraStepFactory = Callable[[AppContext], Sequence[StepDefinition]]


@dataclass(frozen=True, slots=True)
class DailyTaskSet:
    """一个 App 选择使用的任务集合，不要求所有 App 实现同样的流程。"""

    content: TaskHandler | None = None
    check_in: TaskHandler | None = None
    balance: TaskHandler | None = None
    duration_reward: TaskHandler | None = None
    ad_reward: TaskHandler | None = None


@dataclass(frozen=True, slots=True)
class DailyWorkflowBuilder:
    """组合当前奖励类 App 的默认步骤；其他 App 可以提供自己的构建器。"""

    spec: AppSpec
    navigation: NavigationController
    tasks: DailyTaskSet
    extra_steps: ExtraStepFactory | None = None

    def build(self, context: AppContext) -> WorkflowDefinition:
        steps = [
            StepDefinition(
                "启动应用",
                "启动应用",
                self._start_app,
                required=True,
                max_attempts=2,
                continue_on_failure=False,
                recovery=self.navigation.restart_app,
                allow_interruption_after=False,
            ),
            StepDefinition(
                "处理启动弹窗",
                "处理启动弹窗",
                self._dismiss_launch,
                capture_on_failure=False,
                allow_interruption_after=False,
            ),
        ]
        steps.extend(self.build_business_steps(context))
        return WorkflowDefinition(
            "daily",
            f"{self.spec.display_name}每日任务",
            tuple(steps),
        )

    def build_business_steps(self, context: AppContext) -> list[StepDefinition]:
        items: list[StepDefinition] = []
        if self.tasks.content is not None:
            items.append(
                StepDefinition(
                    "浏览内容",
                    "浏览内容",
                    self.tasks.content,
                    required=True,
                    recovery=self.navigation.recover_home,
                )
            )

        if self.tasks.check_in is not None:
            check_in = StepDefinition(
                "每日签到",
                "每日签到",
                self.tasks.check_in,
                recovery=self.navigation.recover_home,
            )
            first_probability = float(context.option("first_check_in_probability", 0.5))
            insert_at = 0 if context.random.random() < first_probability else len(items)
            items.insert(insert_at, check_in)
        if self.tasks.duration_reward is not None:
            items.append(
                StepDefinition(
                    "领取时段奖励",
                    "领取时段奖励",
                    self.tasks.duration_reward,
                    recovery=self.navigation.recover_home,
                )
            )
        if self.tasks.ad_reward is not None:
            probability = float(context.option("execute_ad_probability", 0.8))
            if context.random.random() < probability:
                items.append(
                    StepDefinition(
                        "广告奖励",
                        "广告奖励",
                        self.tasks.ad_reward,
                        recovery=self.navigation.recover_home,
                    )
                )

        if self.extra_steps is not None:
            items.extend(self.extra_steps(context))

        if self.tasks.balance is not None:
            balance = StepDefinition(
                "随机记录余额",
                "记录余额",
                self.tasks.balance,
                recovery=self.navigation.recover_home,
            )
            items.insert(context.random.randint(0, len(items)), balance)
            # 随机位置失败时收尾再试一次，成功后任务自身会跳过。
            items.append(
                StepDefinition(
                    "余额兜底记录",
                    "确认余额记录",
                    self.tasks.balance,
                    recovery=self.navigation.recover_home,
                )
            )
        return items

    def _start_app(self, context: AppContext) -> StepOutcome:
        result = context.session.start_app(self.spec.identity)
        if not result.succeeded:
            return StepOutcome.failure(f"启动应用失败: {result.message}")
        context.timing.wait(float(context.option("launch_wait_seconds", 6.0)))
        return StepOutcome.success("应用启动完成")

    def _dismiss_launch(self, context: AppContext) -> StepOutcome:
        closed = self.navigation.dismiss_launch(context)
        return StepOutcome.success("启动弹窗处理完成", closed_count=closed)
