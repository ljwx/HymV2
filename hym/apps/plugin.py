from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from hym.apps.specs import (
    AppSpec,
    AudioContentSpec,
    CheckInSpec,
    CheckInStageSpec,
    ContentSpec,
    NewsContentSpec,
    VideoContentSpec,
)
from hym.core.events import EventLevel
from hym.core.models import Observation, SystemKey, WorkflowResult, WorkflowStatus
from hym.core.targets import ResolveResult, TargetSpec
from hym.runtime.ads import AdStateMachine
from hym.runtime.context import AppContext, DailyActionStatus
from hym.runtime.navigation import NavigationController
from hym.runtime.video import VideoContentClassifier, VideoContentKind, VideoWatchPlanner
from hym.runtime.workflow import (
    StepDefinition,
    StepOutcome,
    WorkflowDefinition,
    WorkflowExecutor,
)


@dataclass(slots=True)
class ConfiguredAppPlugin:
    """根据 AppSpec 组合公共流程，App 只声明差异。"""

    spec: AppSpec
    content_handlers: Mapping[str, Callable[[AppContext, ContentSpec], StepOutcome]] | None = None
    _handlers: dict[str, Callable[[AppContext, ContentSpec], StepOutcome]] = field(
        init=False,
        repr=False,
    )
    _navigation: NavigationController = field(init=False, repr=False)
    _video_classifier: VideoContentClassifier = field(
        default_factory=VideoContentClassifier,
        init=False,
        repr=False,
    )
    _video_watch_planner: VideoWatchPlanner = field(
        default_factory=VideoWatchPlanner,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        self._navigation = NavigationController(self.spec)
        self._handlers = {
            "video": self._browse_video_content,
            "news": self._browse_news_content,
            "audio": self._browse_audio_content,
        }
        self._handlers.update(self.content_handlers or {})

    def register_content_handler(
        self,
        kind: str,
        handler: Callable[[AppContext, ContentSpec], StepOutcome],
    ) -> None:
        """注册新的内容策略时不需要修改工作流调度代码。"""

        if not kind:
            raise ValueError("内容类型不能为空")
        self._handlers[kind] = handler

    def build_app_steps(self, context: AppContext) -> Sequence[StepDefinition]:
        """App 独有任务扩展点，默认放在公共奖励任务之后执行。"""

        return ()

    @property
    def app_id(self) -> str:
        return self.spec.identity.app_id

    def run(self, context: AppContext) -> WorkflowResult:
        definition = self.build_workflow(context)
        return WorkflowExecutor().run(
            context,
            definition.workflow_id,
            definition.display_name,
            definition.steps,
        )

    def build_workflow(self, context: AppContext) -> WorkflowDefinition:
        """构造本轮稳定步骤计划，运行器可按步骤切片执行。"""

        steps = [
            StepDefinition(
                "启动应用",
                "启动应用",
                self._start_app,
                required=True,
                max_attempts=2,
                continue_on_failure=False,
                recovery=self._restart_app,
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
        business_steps = self._business_steps(context)
        steps.extend(business_steps)
        return WorkflowDefinition(
            "daily",
            f"{self.spec.display_name}每日任务",
            tuple(steps),
        )

    def _business_steps(self, context: AppContext) -> list[StepDefinition]:
        content = StepDefinition(
            "浏览内容",
            "浏览内容",
            self._browse_content,
            required=True,
            recovery=self._recover_home,
        )
        check_in = StepDefinition(
            "每日签到",
            "每日签到",
            self._check_in,
            recovery=self._recover_home,
        )
        duration_reward = StepDefinition(
            "领取时段奖励",
            "领取时段奖励",
            self._duration_reward,
            recovery=self._recover_home,
        )
        ad_reward = StepDefinition(
            "广告奖励",
            "广告奖励",
            self._ad_reward,
            recovery=self._recover_home,
        )

        items: list[StepDefinition] = [content]
        if self.spec.check_in is not None:
            first_probability = float(context.option("first_check_in_probability", 0.5))
            items.insert(0 if context.random.random() < first_probability else 1, check_in)
        if self.spec.duration_reward is not None:
            items.append(duration_reward)
        if self.spec.ad is not None and self.spec.ad_entry is not None:
            probability = float(context.option("execute_ad_probability", 0.8))
            if context.random.random() < probability:
                items.append(ad_reward)

        # 真正的 App 独有任务由对应插件追加，公共执行器不感知其业务细节。
        items.extend(self.build_app_steps(context))

        if self.spec.balance is not None:
            balance = StepDefinition(
                "随机记录余额",
                "记录余额",
                self._record_balance,
                recovery=self._recover_home,
            )
            items.insert(context.random.randint(0, len(items)), balance)
            # 随机节点失败时在收尾再尝试，成功后该步骤会自动跳过。
            items.append(
                StepDefinition(
                    "余额兜底记录",
                    "确认余额记录",
                    self._record_balance,
                    recovery=self._recover_home,
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
        closed = self._navigation.dismiss_launch(context)
        return StepOutcome.success("启动弹窗处理完成", closed_count=closed)

    def _go_home(self, context: AppContext, *, select_tab: bool = False) -> bool:
        return self._navigation.go_home(context, select_tab=select_tab)

    def _go_task_page(self, context: AppContext) -> bool:
        return self._navigation.go_task_page(context)

    def _check_in(self, context: AppContext) -> StepOutcome:
        if context.daily_value("check_in") is not None:
            return StepOutcome(WorkflowStatus.ALREADY_DONE, "今天已经完成签到")
        checkpoint = context.daily_action_status("check_in")
        if checkpoint is DailyActionStatus.CONFIRMED:
            context.mark_daily("check_in", True)
            return StepOutcome(WorkflowStatus.ALREADY_DONE, "签到检查点显示今天已经完成")
        spec = self.spec.check_in
        if spec is None:
            return StepOutcome.skipped("当前应用没有签到流程")
        if not self._go_task_page(context):
            return StepOutcome.failure("无法进入任务页")

        if self.spec.ad is not None:
            for _ in range(spec.pre_ad_attempts):
                if context.actions.resolve_many(self.spec.ad.start_markers, include_screenshot=True) is None:
                    break
                AdStateMachine().run(context, self.spec.ad)
            if spec.pre_ad_attempts and not self._go_task_page(context):
                return StepOutcome.failure("签到前置广告结束后无法恢复任务页")
        return self._run_check_in_states(context, spec, checkpoint)

    def _run_check_in_states(
        self,
        context: AppContext,
        spec: CheckInSpec,
        checkpoint: DailyActionStatus,
    ) -> StepOutcome:
        """复用一次页面观察匹配当前阶段，视觉能力只在结构匹配失败时启用。"""

        executed: set[str] = set()
        committed = checkpoint in {
            DailyActionStatus.PENDING_CONFIRMATION,
            DailyActionStatus.UNCERTAIN,
        }
        for _ in range(spec.max_transitions + 1):
            # 提交动作结果不确定时只查成功证据，不能再次领取。
            pending_stages = () if committed else tuple(
                stage for stage in spec.stages if stage.stage_id not in executed
            )
            targets = tuple(spec.success_targets) + tuple(spec.passive_success_targets) + tuple(
                target
                for stage in pending_stages
                for target in (*stage.state_markers, *stage.action_targets)
            )
            observation = context.actions.observe_for(targets, include_screenshot=False)
            state = self._match_check_in_state(context, spec, pending_stages, observation)
            if state is None and context.actions.needs_screenshot(targets):
                observation = context.actions.observe_for(targets, include_screenshot=True)
                state = self._match_check_in_state(context, spec, pending_stages, observation)
            if state is None:
                break

            kind, stage, target, resolved = state
            if kind == "success":
                return self._finish_check_in(context, spec, committed, target.target_id)
            if stage is None or resolved.target is None:
                break
            context.emit(
                "reward.check_in.stage.matched",
                "签到状态命中",
                f"当前签到阶段: {stage.stage_id}",
                workflow_id="daily",
                step_id="每日签到",
                status="matched",
                data={
                    "stage_id": stage.stage_id,
                    "target_id": target.target_id,
                    "strategy_id": resolved.target.strategy_id,
                    "evidence": resolved.target.evidence,
                },
            )
            if stage.commit_action and not committed:
                context.mark_daily_action(
                    "check_in",
                    DailyActionStatus.PENDING_CONFIRMATION,
                    workflow_id="daily",
                    step_id="每日签到",
                    stage_id=stage.stage_id,
                    target_id=target.target_id,
                )
                committed = True
            if not context.actions.tap_resolved(resolved.target):
                if committed:
                    context.mark_daily_action(
                        "check_in",
                        DailyActionStatus.UNCERTAIN,
                        workflow_id="daily",
                        step_id="每日签到",
                        stage_id=stage.stage_id,
                        reason="点击结果失败",
                    )
                return StepOutcome.failure(f"签到阶段点击失败: {stage.stage_id}")
            executed.add(stage.stage_id)
            if stage.wait_seconds is None:
                context.timing.operation_delay()
            else:
                context.timing.wait(stage.wait_seconds)

        if committed:
            context.mark_daily_action(
                "check_in",
                DailyActionStatus.UNCERTAIN,
                workflow_id="daily",
                step_id="每日签到",
                reason="状态流结束后未见成功信号",
            )
            return StepOutcome.failure("签到动作已执行，但没有识别到完成状态")
        return StepOutcome.failure("当前页面没有匹配到可执行的签到分支")

    def _match_check_in_state(
        self,
        context: AppContext,
        spec: CheckInSpec,
        stages: Sequence[CheckInStageSpec],
        observation: Observation | None,
    ) -> tuple[str, CheckInStageSpec | None, TargetSpec, ResolveResult] | None:
        if observation is None:
            return None
        success = self._resolve_first_in(context, spec.success_targets, observation)
        if success is not None:
            return "success", None, success[0], success[1]
        for stage in stages:
            if stage.state_markers and self._resolve_first_in(
                context,
                stage.state_markers,
                observation,
            ) is None:
                continue
            action = self._resolve_first_in(context, stage.action_targets, observation)
            if action is not None:
                return "action", stage, action[0], action[1]
        passive_success = self._resolve_first_in(
            context,
            spec.passive_success_targets,
            observation,
        )
        if passive_success is not None:
            return "success", None, passive_success[0], passive_success[1]
        return None

    def _finish_check_in(
        self,
        context: AppContext,
        spec: CheckInSpec,
        committed: bool,
        evidence_target_id: str,
    ) -> StepOutcome:
        context.mark_daily_action(
            "check_in",
            DailyActionStatus.CONFIRMED,
            workflow_id="daily",
            step_id="每日签到",
            evidence_target_id=evidence_target_id,
        )
        context.mark_daily("check_in", True)
        context.emit(
            "reward.check_in.recorded",
            "签到结果记录",
            "今日签到成功",
            workflow_id="daily",
            step_id="每日签到",
            status="success",
            data={"evidence_target_id": evidence_target_id},
        )
        if spec.post_ad_target is not None and self.spec.ad is not None:
            if context.actions.tap_target(spec.post_ad_target, timeout=1.0):
                AdStateMachine().run(context, self.spec.ad)
        if spec.close_with_back:
            context.actions.press(SystemKey.BACK)
        elif spec.close_target is not None:
            context.actions.tap_target(spec.close_target, timeout=1.0)
        if committed:
            return StepOutcome.success("签到完成")
        return StepOutcome(WorkflowStatus.ALREADY_DONE, "页面显示今天已经签到")

    def _record_balance(self, context: AppContext) -> StepOutcome:
        if context.daily_value("balance") is not None:
            return StepOutcome(WorkflowStatus.ALREADY_DONE, "今天已经记录过余额")
        spec = self.spec.balance
        if spec is None:
            return StepOutcome.skipped("当前应用没有余额流程")
        if not self._go_task_page(context):
            return StepOutcome.failure("记录余额时无法进入任务页")
        if spec.enter_target is not None:
            if not context.actions.tap_target(spec.enter_target, timeout=2.0):
                return StepOutcome.failure("没有找到余额页面入口")
            context.timing.operation_delay()
        if spec.page_marker is not None and not context.actions.exists(spec.page_marker, timeout=3.0):
            return StepOutcome.failure("进入余额页面后没有找到页面标记")

        result = context.actions.resolve(spec.balance_target, timeout=3.0)
        if not result.found or result.target is None:
            return StepOutcome.failure("没有识别到余额区域")
        artifacts = ()
        value = result.target.evidence or ""
        if spec.screenshot_only or re.search(r"\d", value) is None:
            artifacts = context.diagnostics.capture(f"{self.spec.identity.app_id}-balance")
            value = "页面截图"
        context.mark_daily(
            "balance",
            {"value": value, "artifacts": [artifact.uri for artifact in artifacts]},
        )
        context.emit(
            "reward.balance.recorded",
            "余额记录完成",
            f"今日余额已记录: {value}",
            workflow_id="daily",
            step_id="记录余额",
            status="success",
            data={"value": value},
            artifacts=artifacts,
        )
        if spec.close_with_back:
            context.actions.press(SystemKey.BACK)
        return StepOutcome(WorkflowStatus.SUCCESS, "余额记录完成", {"value": value}, artifacts)

    def _duration_reward(self, context: AppContext) -> StepOutcome:
        spec = self.spec.duration_reward
        if spec is None:
            return StepOutcome.skipped("当前应用没有时段奖励")
        if not self._go_task_page(context):
            return StepOutcome.failure("领取时段奖励时无法进入任务页")
        if not context.actions.tap_target(spec.reward_target, timeout=2.0):
            return StepOutcome.skipped("当前没有可领取的时段奖励")
        context.timing.operation_delay()
        if spec.success_target is not None and not context.actions.exists(spec.success_target, timeout=5.0):
            return StepOutcome.failure("已点击时段奖励，但没有识别到到账提示")
        ad_outcome: StepOutcome | None = None
        if spec.ad_target is not None and self.spec.ad is not None:
            if context.actions.tap_target(spec.ad_target, timeout=1.0):
                ad_outcome = AdStateMachine().run(context, self.spec.ad)
        if spec.close_target is not None:
            context.actions.tap_target(spec.close_target, timeout=1.0)
        if ad_outcome is not None and ad_outcome.status is not WorkflowStatus.SUCCESS:
            return StepOutcome(
                WorkflowStatus.PARTIAL,
                "时段奖励已领取，但附加广告未完整结束",
                {
                    "ad_status": ad_outcome.status.value,
                    "ad_message": ad_outcome.message,
                },
            )
        return StepOutcome.success("时段奖励领取完成")

    def _ad_reward(self, context: AppContext) -> StepOutcome:
        if self.spec.ad is None or self.spec.ad_entry is None:
            return StepOutcome.skipped("当前应用没有广告奖励")
        total = context.sample_count("ad_task_count", 1, 3)
        completed = 0
        uncertain = 0
        failed = 0
        for index in range(1, total + 1):
            context.emit(
                "reward.ad.item.started",
                "广告任务开始",
                f"开始执行第 {index}/{total} 个广告任务",
                workflow_id="daily",
                step_id="广告奖励",
                status="running",
                data={"index": index, "total": total},
            )
            if not self._go_task_page(context):
                failed += 1
                context.emit(
                    "reward.ad.item.finished",
                    "广告任务结束",
                    f"第 {index}/{total} 个广告任务无法进入任务页",
                    level=EventLevel.WARNING,
                    workflow_id="daily",
                    step_id="广告奖励",
                    status="failed",
                    data={"index": index, "total": total},
                )
                continue
            entered = False
            search_swipes = int(context.option("ad_entry_search_swipes", 2))
            for attempt in range(search_swipes + 1):
                if context.actions.tap_target(self.spec.ad_entry, timeout=1.0):
                    entered = True
                    break
                if attempt >= search_swipes:
                    break
                context.actions.swipe_up()
                context.timing.operation_delay()
            if not entered:
                failed += 1
                context.emit(
                    "reward.ad.item.finished",
                    "广告任务结束",
                    f"第 {index}/{total} 个广告任务没有找到入口",
                    level=EventLevel.WARNING,
                    workflow_id="daily",
                    step_id="广告奖励",
                    status="failed",
                    data={"index": index, "total": total},
                )
                self._recover_home(context)
                continue
            outcome = AdStateMachine().run(context, self.spec.ad)
            if outcome.status is WorkflowStatus.SUCCESS:
                completed += 1
            elif outcome.status is WorkflowStatus.PARTIAL:
                uncertain += 1
            else:
                failed += 1
                self._recover_home(context)
            context.emit(
                "reward.ad.item.finished",
                "广告任务结束",
                f"第 {index}/{total} 个广告任务执行结果: {outcome.message}",
                level=(
                    EventLevel.INFO
                    if outcome.status is WorkflowStatus.SUCCESS
                    else EventLevel.WARNING
                ),
                workflow_id="daily",
                step_id="广告奖励",
                status=outcome.status.value,
                data={
                    "index": index,
                    "total": total,
                    "result": outcome.status.value,
                },
            )
        outputs = {
            "completed": completed,
            "uncertain": uncertain,
            "failed": failed,
            "total": total,
        }
        if completed == 0 and uncertain == 0:
            return StepOutcome.failure("广告任务没有完成，但不会阻断后续流程")
        if completed < total:
            return StepOutcome(
                WorkflowStatus.PARTIAL,
                "广告任务仅部分确认完成",
                outputs,
            )
        return StepOutcome.success("广告任务完成", **outputs)

    def _browse_content(self, context: AppContext) -> StepOutcome:
        if bool(context.option("skip_content", False)):
            return StepOutcome.skipped("配置为跳过内容浏览")
        handler = self._handlers.get(self.spec.content_kind)
        if handler is None:
            return StepOutcome.failure(
                f"没有注册内容策略: {self.spec.content_kind or '未知类型'}",
                retryable=False,
            )
        return handler(context, self.spec.content)

    def _browse_video_content(self, context: AppContext, spec: ContentSpec) -> StepOutcome:
        if not isinstance(spec, VideoContentSpec):
            return StepOutcome.failure("视频内容配置类型不正确", retryable=False)
        return self._browse_video(context, spec)

    def _browse_news_content(self, context: AppContext, spec: ContentSpec) -> StepOutcome:
        if not isinstance(spec, NewsContentSpec):
            return StepOutcome.failure("新闻内容配置类型不正确", retryable=False)
        return self._browse_news(context, spec)

    def _browse_audio_content(self, context: AppContext, spec: ContentSpec) -> StepOutcome:
        if not isinstance(spec, AudioContentSpec):
            return StepOutcome.failure("音频内容配置类型不正确", retryable=False)
        if not self._go_home(context, select_tab=True):
            return StepOutcome.failure("音频播放前无法进入首页")
        if not self._ensure_audio_playing(context, spec):
            return StepOutcome.failure("没有识别到可播放的音频会话")

        progress = context.step_progress("浏览内容")
        if "target_seconds" not in progress:
            progress.update(
                {
                    "content_kind": "audio",
                    "target_seconds": context.sample_seconds(
                        "audio_session_seconds",
                        600.0,
                        1800.0,
                    ),
                    "elapsed_seconds": 0.0,
                    "recovery_count": 0,
                }
            )
        duration = float(progress["target_seconds"])
        check_interval = max(15.0, float(context.option("audio_check_interval_seconds", 60.0)))
        context.emit(
            "content.audio.session.started",
            "音频会话开始",
            "音频已开始播放，进入低频状态确认",
            workflow_id="daily",
            step_id="浏览内容",
            status="running",
            data={"planned_seconds": round(duration, 2), "check_interval_seconds": check_interval},
        )
        elapsed = float(progress.get("elapsed_seconds", 0.0))
        recoveries = int(progress.get("recovery_count", 0))
        while elapsed < duration:
            wait_seconds = min(check_interval, duration - elapsed)
            context.timing.clock.sleep(wait_seconds)
            elapsed += wait_seconds
            # 长时任务只低频确认前台包名，避免持续解析 UI 带来额外开销。
            current = context.actions.observe(include_ui_tree=False, include_screenshot=False)
            if current is not None and current.activity.package_name == self.spec.identity.package_name:
                progress["elapsed_seconds"] = elapsed
                context.reach_safe_point(
                    "content.audio.checkpoint",
                    elapsed_seconds=round(elapsed, 2),
                    target_seconds=round(duration, 2),
                )
                continue
            recoveries += 1
            context.emit(
                "content.audio.session.recovering",
                "音频会话恢复",
                "音频会话离开目标应用，尝试恢复播放",
                level=EventLevel.WARNING,
                workflow_id="daily",
                step_id="浏览内容",
                status="recovering",
                data={
                    "recovery_count": recoveries,
                    "foreground_package": current.activity.package_name if current else "",
                    "foreground_activity": current.activity.activity_name if current else "",
                },
            )
            if not self._go_home(context, select_tab=True):
                return StepOutcome.failure("音频会话离开应用且恢复失败")
            # 重启后 App 可能已经自动续播，不能只查“开始播放”按钮。
            if not self._ensure_audio_playing(context, spec):
                return StepOutcome.failure("音频会话恢复后无法继续播放")
            progress["elapsed_seconds"] = elapsed
            progress["recovery_count"] = recoveries
            context.reach_safe_point(
                "content.audio.checkpoint",
                elapsed_seconds=round(elapsed, 2),
                target_seconds=round(duration, 2),
            )

        context.clear_step_progress("浏览内容")
        return StepOutcome.success(
            "音频浏览会话完成",
            listened_seconds=round(duration, 2),
            recovery_count=recoveries,
        )

    @staticmethod
    def _ensure_audio_playing(context: AppContext, spec: AudioContentSpec) -> bool:
        """复用一次页面观察，接受已播放状态或点击恢复播放。"""

        observation = context.actions.observe_for(
            (spec.resume_target, spec.playing_target, spec.session_marker),
            include_screenshot=False,
        )
        if observation is None or not context.actions.resolve_in(spec.session_marker, observation).found:
            return False
        if context.actions.resolve_in(spec.playing_target, observation).found:
            return True
        resume = context.actions.resolve_in(spec.resume_target, observation)
        if not resume.found or resume.target is None:
            return False
        if not context.actions.tap_resolved(resume.target):
            return False
        context.timing.operation_delay()
        return True

    def _browse_video(self, context: AppContext, spec: VideoContentSpec) -> StepOutcome:
        if not self._go_home(context, select_tab=True):
            return StepOutcome.failure("无法进入视频首页")
        progress = context.step_progress("浏览内容")
        if "target_count" not in progress:
            progress.update(
                {
                    "content_kind": "video",
                    "target_count": context.sample_count("content_count", 5, 26),
                    "next_index": 1,
                    "viewed": 0,
                    "normal": 0,
                    "unrecognized_streak": 0,
                }
            )
        count = int(progress["target_count"])
        viewed = int(progress.get("viewed", 0))
        normal_count = int(progress.get("normal", 0))
        unrecognized_streak = int(progress.get("unrecognized_streak", 0))
        recover_after = int(context.option("recover_after_unrecognized_items", 2))
        for index in range(int(progress.get("next_index", 1)), count + 1):
            item_started = context.timing.clock.now()
            context.actions.swipe_up()
            context.timing.clock.sleep(
                context.sample_seconds("content_classify_delay", 0.25, 0.6)
            )
            observation = context.actions.observe_for(
                (spec.feed_marker, *spec.ad_markers, *spec.long_markers, *spec.normal_markers),
                include_screenshot=False,
            )
            if (
                observation is not None
                and observation.activity.package_name
                and observation.activity.package_name != self.spec.identity.package_name
            ):
                context.emit(
                    "content.foreground.left",
                    "内容页离开应用",
                    f"第 {index} 个内容跳到其他应用，开始恢复首页",
                    level=EventLevel.WARNING,
                    workflow_id="daily",
                    step_id="浏览内容",
                    status="recovering",
                    data={
                        "index": index,
                        "foreground_package": observation.activity.package_name,
                    },
                )
                self._recover_home(context)
                continue
            if observation is None or not context.actions.resolve_in(spec.feed_marker, observation).found:
                if observation is not None:
                    target_id = self._dismiss_popup_in(
                        context,
                        self.spec.navigation.home_intercepts,
                        observation,
                    )
                    if target_id is not None:
                        self._emit_popup_dismissed(context, target_id)
                        context.timing.operation_delay()
                        unrecognized_streak = 0
                        continue
                unrecognized_streak += 1
                context.emit(
                    "content.item.skipped",
                    "内容跳过",
                    f"第 {index} 个内容不是可识别的视频项",
                    level=EventLevel.WARNING,
                    workflow_id="daily",
                    step_id="浏览内容",
                    status="skipped",
                    data={"index": index},
                )
                if unrecognized_streak >= recover_after:
                    self._recover_home(context)
                    unrecognized_streak = 0
                continue

            unrecognized_streak = 0

            classification = self._video_classifier.classify(context, spec, observation)
            watch_plan = self._video_watch_planner.plan(
                context,
                classification=classification,
            )
            target_duration = context.sample_seconds(
                watch_plan.duration_prefix,
                *watch_plan.duration_range,
            )
            classification_seconds = max(
                0.0,
                (context.timing.clock.now() - item_started).total_seconds(),
            )
            if classification.kind in {
                VideoContentKind.AD,
                VideoContentKind.SUSPECTED_AD,
            }:
                suspected = classification.kind is VideoContentKind.SUSPECTED_AD
                context.emit(
                    "content.ad.suspected" if suspected else "content.ad.detected",
                    "疑似视频广告" if suspected else "视频广告识别",
                    (
                        f"第 {index} 个内容缺少明确分类标记，按疑似广告快速跳过"
                        if suspected
                        else f"第 {index} 个内容识别为广告，禁止互动"
                    ),
                    workflow_id="daily",
                    step_id="浏览内容",
                    status="success",
                    data={
                        "index": index,
                        "classification_seconds": round(classification_seconds, 2),
                        "classification_kind": classification.kind.value,
                        "classification_reason": classification.reason,
                        "matched_target_id": classification.matched_target_id,
                    },
                )
            minimum_after_classification = context.timing.baseline_seconds(
                watch_plan.post_classification_minimum
            ) if watch_plan.post_classification_minimum > 0 else 0.0
            remaining = max(
                0.0,
                target_duration - classification_seconds,
                minimum_after_classification,
            )
            if remaining > 0:
                context.timing.clock.sleep(remaining)
            duration = max(0.0, (context.timing.clock.now() - item_started).total_seconds())
            viewed += 1
            if classification.kind in {VideoContentKind.NORMAL, VideoContentKind.LONG}:
                normal_count += 1
            if watch_plan.allow_interactions:
                self._video_interactions(context, spec)
            context.emit(
                "content.item.finished",
                "内容浏览完成",
                f"第 {index} 个内容浏览完成，类型: {classification.kind.label}",
                workflow_id="daily",
                step_id="浏览内容",
                status="success",
                data={
                    "index": index,
                    "content_type": classification.kind.label,
                    "classification_kind": classification.kind.value,
                    "classification_reason": classification.reason,
                    "watch_mode": watch_plan.mode,
                    "planned_duration_seconds": round(target_duration, 2),
                    "duration_seconds": round(duration, 2),
                    "classification_seconds": round(classification_seconds, 2),
                    "post_classification_wait_seconds": round(remaining, 2),
                    "video_length_detected": False,
                    "matched_target_id": classification.matched_target_id,
                },
            )
            progress.update(
                {
                    "next_index": index + 1,
                    "viewed": viewed,
                    "normal": normal_count,
                    "unrecognized_streak": unrecognized_streak,
                }
            )
            context.reach_safe_point(
                "content.item.finished",
                index=index,
                requested=count,
                viewed=viewed,
            )

        if viewed == 0:
            context.clear_step_progress("浏览内容")
            return StepOutcome(
                WorkflowStatus.NO_PROGRESS,
                "本轮没有完成任何视频浏览",
                {"requested": count},
            )
        context.clear_step_progress("浏览内容")
        return StepOutcome.success("视频浏览完成", requested=count, viewed=viewed, normal=normal_count)

    def _video_interactions(self, context: AppContext, spec: VideoContentSpec) -> None:
        interaction = spec.interaction
        if interaction.follow_target is not None and context.random.random() < float(
            context.option("follow_probability", 0.011)
        ):
            context.actions.tap_target(interaction.follow_target, timeout=0.8)
        if interaction.like_target is not None and context.random.random() < float(
            context.option("like_probability", 0.17)
        ):
            context.actions.tap_target(interaction.like_target, timeout=1.0)
            context.timing.operation_delay()
        if interaction.comment_target is not None and context.random.random() < float(
            context.option("comment_probability", 0.05)
        ):
            if context.actions.tap_target(interaction.comment_target, timeout=1.0):
                context.timing.operation_delay(2)
                context.actions.press(SystemKey.BACK)
                context.timing.operation_delay()
        if interaction.profile_target is not None and context.random.random() < float(
            context.option("works_probability", 0.12)
        ):
            self._browse_author_works(context, spec)

    def _browse_author_works(self, context: AppContext, spec: VideoContentSpec) -> None:
        interaction = spec.interaction
        if interaction.profile_target is None or not context.actions.tap_target(
            interaction.profile_target,
            timeout=1.0,
        ):
            return
        context.timing.operation_delay()
        if interaction.profile_marker is not None and not context.actions.exists(
            interaction.profile_marker,
            timeout=2.0,
        ):
            context.actions.press(SystemKey.BACK)
            return
        count = context.sample_count("works_count", 1, 5)
        for _ in range(count):
            if interaction.work_item_target is None or not context.actions.tap_target(
                interaction.work_item_target,
                timeout=1.5,
            ):
                context.actions.swipe_up()
                continue
            context.timing.clock.sleep(
                context.sample_seconds("normal_duration", 10.0, 30.0)
            )
            context.actions.press(SystemKey.BACK)
            context.timing.operation_delay()
            context.actions.swipe_up()
        context.actions.press(SystemKey.BACK)

    def _browse_news(self, context: AppContext, spec: NewsContentSpec) -> StepOutcome:
        if not self._go_home(context, select_tab=True):
            return StepOutcome.failure("无法进入新闻首页")
        progress = context.step_progress("浏览内容")
        if "target_count" not in progress:
            progress.update(
                {
                    "content_kind": "news",
                    "target_count": context.sample_count("content_count", 5, 15),
                    "next_index": 1,
                    "viewed": 0,
                }
            )
        count = int(progress["target_count"])
        viewed = int(progress.get("viewed", 0))
        for index in range(int(progress.get("next_index", 1)), count + 1):
            if not context.actions.tap_target(spec.feed_item, timeout=2.0):
                context.actions.swipe_up()
                context.timing.operation_delay()
                continue
            context.timing.wait(float(context.option("detail_wait_seconds", 3.0)))
            if not context.actions.exists(spec.detail_marker, timeout=2.0):
                context.actions.press(SystemKey.BACK)
                context.actions.swipe_up()
                continue

            read_to_bottom = context.random.random() < float(context.option("read_to_bottom_probability", 0.75))
            scroll_prefix = "news_bottom_swipes" if read_to_bottom else "news_partial_swipes"
            scroll_min, scroll_max = ((4, 8) if read_to_bottom else (1, 3))
            for _ in range(context.sample_count(scroll_prefix, scroll_min, scroll_max)):
                context.actions.swipe_up()
                context.timing.clock.sleep(
                    context.sample_seconds("news_scroll_pause_seconds", 1.5, 4.0)
                )
                if read_to_bottom and spec.bottom_marker is not None:
                    if context.actions.exists(spec.bottom_marker, timeout=0.4):
                        break
            if spec.like_target is not None and context.random.random() < float(
                context.option("like_probability", 0.17)
            ):
                context.actions.tap_target(spec.like_target, timeout=0.8)
            if spec.comment_target is not None and context.random.random() < float(
                context.option("comment_probability", 0.15)
            ):
                if context.actions.tap_target(spec.comment_target, timeout=0.8):
                    context.timing.operation_delay(2)
                    context.actions.press(SystemKey.BACK)
            viewed += 1
            context.actions.press(SystemKey.BACK)
            context.timing.operation_delay()
            context.actions.swipe_up()
            context.emit(
                "content.item.finished",
                "文章浏览完成",
                f"第 {index} 篇文章浏览完成",
                workflow_id="daily",
                step_id="浏览内容",
                status="success",
                data={"index": index, "read_to_bottom": read_to_bottom},
            )
            progress.update({"next_index": index + 1, "viewed": viewed})
            context.reach_safe_point(
                "content.item.finished",
                index=index,
                requested=count,
                viewed=viewed,
            )
        if viewed == 0:
            context.clear_step_progress("浏览内容")
            return StepOutcome(
                WorkflowStatus.NO_PROGRESS,
                "本轮没有完成任何文章浏览",
                {"requested": count},
            )
        context.clear_step_progress("浏览内容")
        return StepOutcome.success("文章浏览完成", requested=count, viewed=viewed)

    def _recover_home(self, context: AppContext) -> None:
        self._navigation.recover_home(context)

    def _restart_app(self, context: AppContext) -> None:
        self._navigation.restart_app(context)

    def _hard_restart_app(self, context: AppContext) -> None:
        self._navigation.hard_restart_app(context)

    @staticmethod
    def _resolve_first_in(
        context: AppContext,
        targets: Sequence[TargetSpec],
        observation: Observation,
    ) -> tuple[TargetSpec, ResolveResult] | None:
        for target in targets:
            result = context.actions.resolve_in(target, observation)
            if result.found:
                return target, result
        return None

    def _dismiss_popup_in(
        self,
        context: AppContext,
        popups,
        observation: Observation,
    ) -> str | None:
        return self._navigation.dismiss_popup_in(context, popups, observation)

    def _emit_popup_dismissed(self, context: AppContext, target_id: str) -> None:
        self._navigation.emit_popup_dismissed(context, target_id)
