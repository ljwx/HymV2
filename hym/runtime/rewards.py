from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from hym.apps.specs import AppSpec, BalanceAssetSpec, CheckInSpec, CheckInStageSpec
from hym.core.events import EventLevel
from hym.core.models import Observation, SystemKey, WorkflowStatus
from hym.core.targets import ResolveResult, TargetSpec
from hym.runtime.ads import AdStateMachine
from hym.runtime.context import AppContext, DailyActionStatus
from hym.runtime.workflow import StepOutcome


TaskPageNavigator = Callable[[AppContext], bool]
HomeRecovery = Callable[[AppContext], None]


@dataclass(frozen=True, slots=True)
class CheckInTask:
    """执行可复用的多阶段签到；特殊签到可由 App 换成自己的任务。"""

    app_spec: AppSpec
    go_task_page: TaskPageNavigator

    def run(self, context: AppContext) -> StepOutcome:
        if context.daily_value("check_in") is not None:
            return StepOutcome(WorkflowStatus.ALREADY_DONE, "今天已经完成签到")
        checkpoint = context.daily_action_status("check_in")
        if checkpoint is DailyActionStatus.CONFIRMED:
            context.mark_daily("check_in", True)
            return StepOutcome(
                WorkflowStatus.ALREADY_DONE,
                "签到检查点显示今天已经完成",
            )
        spec = self.app_spec.check_in
        if spec is None:
            return StepOutcome.skipped("当前应用没有签到流程")
        if not self.go_task_page(context):
            return StepOutcome.failure("无法进入任务页")

        if self.app_spec.ad is not None:
            for _ in range(spec.pre_ad_attempts):
                if context.actions.resolve_many(
                    self.app_spec.ad.start_markers,
                    include_screenshot=True,
                ) is None:
                    break
                AdStateMachine().run(context, self.app_spec.ad)
            if spec.pre_ad_attempts and not self.go_task_page(context):
                return StepOutcome.failure("签到前置广告结束后无法恢复任务页")
        return self._run_states(context, spec, checkpoint)

    def _run_states(
        self,
        context: AppContext,
        spec: CheckInSpec,
        checkpoint: DailyActionStatus,
    ) -> StepOutcome:
        """按当前页面动态选择阶段，结构失败后才补视觉观察。"""

        executed: set[str] = set()
        committed = checkpoint in {
            DailyActionStatus.PENDING_CONFIRMATION,
            DailyActionStatus.UNCERTAIN,
        }
        for _ in range(spec.max_transitions + 1):
            # 已提交但未确认时只找成功证据，避免重复领取。
            pending_stages = () if committed else tuple(
                stage for stage in spec.stages if stage.stage_id not in executed
            )
            targets = tuple(spec.success_targets) + tuple(spec.passive_success_targets) + tuple(
                target
                for stage in pending_stages
                for target in (*stage.state_markers, *stage.action_targets)
            )
            observation = context.actions.observe_for(targets, include_screenshot=False)
            state = self._match_state(context, spec, pending_stages, observation)
            if state is None and context.actions.needs_screenshot(targets):
                observation = context.actions.observe_for(targets, include_screenshot=True)
                state = self._match_state(context, spec, pending_stages, observation)
            if state is None:
                break

            kind, stage, target, resolved = state
            if kind == "success":
                return self._finish(context, spec, committed, target.target_id)
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

    def _match_state(
        self,
        context: AppContext,
        spec: CheckInSpec,
        stages: Sequence[CheckInStageSpec],
        observation: Observation | None,
    ) -> tuple[str, CheckInStageSpec | None, TargetSpec, ResolveResult] | None:
        if observation is None:
            return None
        success = _resolve_first_in(context, spec.success_targets, observation)
        if success is not None:
            return "success", None, success[0], success[1]
        for stage in stages:
            if stage.state_markers and _resolve_first_in(
                context,
                stage.state_markers,
                observation,
            ) is None:
                continue
            action = _resolve_first_in(context, stage.action_targets, observation)
            if action is not None:
                return "action", stage, action[0], action[1]
        passive = _resolve_first_in(context, spec.passive_success_targets, observation)
        if passive is not None:
            return "success", None, passive[0], passive[1]
        return None

    def _finish(
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
        if spec.post_ad_target is not None and self.app_spec.ad is not None:
            if context.actions.tap_target(spec.post_ad_target, timeout=1.0):
                AdStateMachine().run(context, self.app_spec.ad)
        if spec.close_with_back:
            context.actions.press(SystemKey.BACK)
        elif spec.close_target is not None:
            context.actions.tap_target(spec.close_target, timeout=1.0)
        if committed:
            return StepOutcome.success("签到完成")
        return StepOutcome(WorkflowStatus.ALREADY_DONE, "页面显示今天已经签到")


@dataclass(frozen=True, slots=True)
class BalanceTask:
    """记录单个 App 当天的余额证据。"""

    app_spec: AppSpec
    go_task_page: TaskPageNavigator

    def run(self, context: AppContext) -> StepOutcome:
        recorded = context.daily_value("balance")
        if _has_recorded_balance(recorded):
            return StepOutcome(WorkflowStatus.ALREADY_DONE, "今天已经记录过余额")
        spec = self.app_spec.balance
        if spec is None:
            return StepOutcome.skipped("当前应用没有余额流程")
        if not self.go_task_page(context):
            return StepOutcome.failure("记录余额时无法进入任务页")
        if spec.enter_target is not None:
            if not context.actions.tap_target(spec.enter_target, timeout=2.0):
                return StepOutcome.failure("没有找到余额页面入口")
            if spec.enter_wait_seconds is None:
                context.timing.operation_delay()
            else:
                context.timing.wait(spec.enter_wait_seconds)
        if spec.page_marker is not None and not context.actions.exists(
            spec.page_marker,
            timeout=3.0,
        ):
            return StepOutcome.failure("进入余额页面后没有找到页面标记")

        if spec.assets:
            return self._record_assets(context, spec.assets, spec.close_with_back)

        assert spec.balance_target is not None
        result = context.actions.resolve(spec.balance_target, timeout=3.0)
        if not result.found or result.target is None:
            return StepOutcome.failure("没有识别到余额区域")
        artifacts = ()
        value = result.target.evidence or ""
        if spec.screenshot_only or re.search(r"\d", value) is None:
            artifacts = context.diagnostics.capture(f"{self.app_spec.identity.app_id}-balance")
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
            data={"business_date": context.business_date.isoformat(), "value": value},
            artifacts=artifacts,
        )
        if spec.close_with_back:
            context.actions.press(SystemKey.BACK)
        return StepOutcome(
            WorkflowStatus.SUCCESS,
            "余额记录完成",
            {"value": value},
            artifacts,
        )

    def _record_assets(
        self,
        context: AppContext,
        assets: tuple[BalanceAssetSpec, ...],
        close_with_back: bool,
    ) -> StepOutcome:
        observation = context.actions.observe_for(
            tuple(asset.target for asset in assets),
            include_screenshot=True,
        )
        if observation is None or observation.screenshot is None:
            return StepOutcome.failure("余额页面截图失败")

        values: list[dict[str, object]] = []
        missing: list[str] = []
        for asset in assets:
            result = context.actions.resolve_in(asset.target, observation)
            evidence = result.target.evidence if result.found and result.target is not None else None
            amount_minor = _amount_minor(evidence, asset.scale)
            if amount_minor is None:
                missing.append(asset.asset_label)
                continue
            values.append(
                {
                    "asset_key": asset.asset_key,
                    "asset_label": asset.asset_label,
                    "amount_minor": amount_minor,
                    "scale": asset.scale,
                    "unit": asset.unit,
                }
            )
        if missing:
            return StepOutcome.failure(f"没有识别到余额字段: {'、'.join(missing)}")

        data = {
            "business_date": context.business_date.isoformat(),
            "balances": values,
        }
        context.mark_daily("balance", data)
        summary = "，".join(
            f"{item['asset_label']} {_format_minor(int(item['amount_minor']), int(item['scale']))}{item['unit']}"
            for item in values
        )
        context.emit(
            "reward.balance.recorded",
            "余额记录完成",
            f"今日余额已记录: {summary}",
            workflow_id="daily",
            step_id="记录余额",
            status="success",
            data=data,
        )
        if close_with_back:
            context.actions.press(SystemKey.BACK)
        return StepOutcome.success("余额记录完成", balances=values)


def _has_recorded_balance(recorded: object) -> bool:
    if not isinstance(recorded, dict):
        return False
    value = recorded.get("value")
    if not isinstance(value, dict):
        return False
    return bool(value.get("balances") or value.get("value"))


def _amount_minor(value: str | None, scale: int) -> int | None:
    if not value:
        return None
    match = re.search(r"[-+]?\s*\d[\d,]*(?:\.\d+)?", value)
    if match is None:
        return None
    try:
        amount = Decimal(match.group(0).replace(" ", "").replace(",", ""))
        factor = Decimal(10) ** scale
        return int((amount * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except InvalidOperation:
        return None


def _format_minor(value: int, scale: int) -> str:
    if scale <= 0:
        return str(value)
    return f"{Decimal(value) / (Decimal(10) ** scale):.{scale}f}"


@dataclass(frozen=True, slots=True)
class DurationRewardTask:
    """领取当前 App 声明的时段奖励。"""

    app_spec: AppSpec
    go_task_page: TaskPageNavigator

    def run(self, context: AppContext) -> StepOutcome:
        spec = self.app_spec.duration_reward
        if spec is None:
            return StepOutcome.skipped("当前应用没有时段奖励")
        if not self.go_task_page(context):
            return StepOutcome.failure("领取时段奖励时无法进入任务页")
        if not context.actions.tap_target(spec.reward_target, timeout=2.0):
            return StepOutcome.skipped("当前没有可领取的时段奖励")
        if spec.result_wait_seconds is None:
            context.timing.operation_delay()
        else:
            context.timing.wait(spec.result_wait_seconds)
        if spec.success_target is not None and not context.actions.exists(
            spec.success_target,
            timeout=5.0,
        ):
            # 结果识别失败也要清理弹窗，避免遮挡后续独立任务。
            if spec.close_target is not None:
                context.actions.tap_target(spec.close_target, timeout=1.0)
            return StepOutcome.failure("已点击时段奖励，但没有识别到到账提示")
        ad_outcome: StepOutcome | None = None
        if spec.ad_target is not None and self.app_spec.ad is not None:
            if context.actions.tap_target(spec.ad_target, timeout=1.0):
                ad_outcome = AdStateMachine().run(context, self.app_spec.ad)
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


@dataclass(frozen=True, slots=True)
class AdRewardTask:
    """执行独立广告奖励；失败只影响当前广告任务。"""

    app_spec: AppSpec
    go_task_page: TaskPageNavigator
    recover_home: HomeRecovery

    def run(self, context: AppContext) -> StepOutcome:
        if self.app_spec.ad is None or self.app_spec.ad_entry is None:
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
            if not self.go_task_page(context):
                failed += 1
                self._emit_finished(context, index, total, "无法进入任务页", "failed")
                continue
            entered = False
            search_swipes = int(context.option("ad_entry_search_swipes", 2))
            for attempt in range(search_swipes + 1):
                if context.actions.tap_target(self.app_spec.ad_entry, timeout=1.0):
                    entered = True
                    break
                if attempt >= search_swipes:
                    break
                context.actions.swipe_up()
                context.timing.operation_delay()
            if not entered:
                failed += 1
                self._emit_finished(context, index, total, "没有找到入口", "failed")
                self.recover_home(context)
                continue
            outcome = AdStateMachine().run(context, self.app_spec.ad)
            if outcome.status is WorkflowStatus.SUCCESS:
                completed += 1
            elif outcome.status is WorkflowStatus.PARTIAL:
                uncertain += 1
            else:
                failed += 1
                self.recover_home(context)
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
                data={"index": index, "total": total, "result": outcome.status.value},
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

    @staticmethod
    def _emit_finished(
        context: AppContext,
        index: int,
        total: int,
        reason: str,
        status: str,
    ) -> None:
        context.emit(
            "reward.ad.item.finished",
            "广告任务结束",
            f"第 {index}/{total} 个广告任务{reason}",
            level=EventLevel.WARNING,
            workflow_id="daily",
            step_id="广告奖励",
            status=status,
            data={"index": index, "total": total},
        )


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
