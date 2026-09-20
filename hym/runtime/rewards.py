from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from hym.apps.specs import (
    AppSpec,
    BalanceAssetSpec,
    CheckInSpec,
    CheckInStageSpec,
    WithdrawalSpec,
)
from hym.core.events import EventLevel
from hym.core.models import Observation, SystemKey, WorkflowStatus
from hym.core.targets import ResolveResult, TargetSpec
from hym.runtime.ads import AdStateMachine
from hym.runtime.context import AppContext, DailyActionStatus
from hym.runtime.workflow import StepOutcome


TaskPageNavigator = Callable[[AppContext], bool]
HomeRecovery = Callable[[AppContext], None]


def _optional_reward_unavailable(context: AppContext, step_id: str, message: str) -> StepOutcome:
    context.emit(
        "reward.optional.unavailable",
        "奖励任务暂不可用",
        message,
        level=EventLevel.WARNING,
        workflow_id="daily",
        step_id=step_id,
        status="skipped",
    )
    return StepOutcome.skipped(message)


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
            return _optional_reward_unavailable(context, "每日签到", "签到时无法进入任务页")

        if self.app_spec.ad is not None:
            for _ in range(spec.pre_ad_attempts):
                if context.actions.resolve_many(
                    self.app_spec.ad.start_markers,
                    include_screenshot=True,
                ) is None:
                    break
                AdStateMachine().run(context, self.app_spec.ad)
            if spec.pre_ad_attempts and not self.go_task_page(context):
                return _optional_reward_unavailable(
                    context,
                    "每日签到",
                    "签到前置广告结束后无法恢复任务页",
                )
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
        return _optional_reward_unavailable(
            context,
            "每日签到",
            "当前页面没有可领取或已完成的签到状态",
        )

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
        option = getattr(context, "option", lambda _key, default: default)
        record_each_run = bool(option("record_balance_each_run", False))
        if not record_each_run and _has_recorded_balance(recorded):
            return StepOutcome(WorkflowStatus.ALREADY_DONE, "今天已经记录过余额")
        spec = self.app_spec.balance
        if spec is None:
            return StepOutcome.skipped("当前应用没有余额流程")
        attempted = context.daily_value("balance_observation_attempted")
        if not record_each_run and _has_daily_boolean(attempted):
            return StepOutcome(WorkflowStatus.ALREADY_DONE, "今天已经尝试记录过余额")
        if not record_each_run:
            context.mark_daily("balance_observation_attempted", True)
        if not self.go_task_page(context):
            return _optional_reward_unavailable(context, "记录余额", "记录余额时无法进入任务页")
        if spec.enter_target is not None:
            if not context.actions.tap_target(spec.enter_target, timeout=2.0):
                return _optional_reward_unavailable(context, "记录余额", "没有找到余额页面入口")
            if spec.enter_wait_seconds is None:
                context.timing.operation_delay()
            else:
                context.timing.wait(spec.enter_wait_seconds)
        if spec.page_marker is not None and not context.actions.exists(
            spec.page_marker,
            timeout=3.0,
        ):
            return _optional_reward_unavailable(
                context,
                "记录余额",
                "进入余额页面后没有找到页面标记",
            )

        if spec.assets:
            return self._record_assets(context, spec.assets, spec.close_with_back)

        assert spec.balance_target is not None
        result = context.actions.resolve(spec.balance_target, timeout=3.0)
        if not result.found or result.target is None:
            return _optional_reward_unavailable(context, "记录余额", "没有识别到余额区域")
        artifacts = ()
        value = result.target.evidence or ""
        if spec.screenshot_only or re.search(r"\d", value) is None:
            artifacts = context.diagnostics.capture(f"{self.app_spec.identity.app_id}-balance")
            value = "页面截图"
        amount_minor = _amount_minor(value, spec.scale)
        balances = [] if amount_minor is None else [
            {
                "asset_key": spec.asset_key,
                "asset_label": spec.asset_label,
                "amount_minor": amount_minor,
                "scale": spec.scale,
                "unit": spec.unit,
            }
        ]
        data = {
            "business_date": context.business_date.isoformat(),
            "value": value,
            "balances": balances,
        }
        context.mark_daily(
            "balance",
            {**data, "artifacts": [artifact.uri for artifact in artifacts]},
        )
        context.emit(
            "reward.balance.recorded",
            "余额记录完成",
            f"今日余额已记录: {value}",
            workflow_id="daily",
            step_id="记录余额",
            status="success",
            data=data,
            artifacts=artifacts,
        )
        if spec.close_with_back:
            context.actions.press(SystemKey.BACK)
        return StepOutcome(
            WorkflowStatus.SUCCESS,
            "余额记录完成",
            {"value": value, "balances": balances},
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
            return _optional_reward_unavailable(context, "记录余额", "余额页面截图失败")

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
            return _optional_reward_unavailable(
                context,
                "记录余额",
                f"没有识别到余额字段: {'、'.join(missing)}",
            )

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


def _has_daily_boolean(recorded: object) -> bool:
    return (
        isinstance(recorded, dict)
        and isinstance(recorded.get("value"), bool)
    )


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
class WithdrawalTask:
    """低频读取提现页，记录余额、提现档位及页面声明的要求。"""

    app_spec: AppSpec
    go_task_page: TaskPageNavigator

    def run(self, context: AppContext) -> StepOutcome:
        spec = self.app_spec.withdrawal
        if spec is None:
            return StepOutcome.skipped("当前应用没有提现信息流程")
        if self._is_fresh(context, spec):
            return StepOutcome(WorkflowStatus.ALREADY_DONE, "提现信息仍在刷新周期内")
        decision = context.daily_value("withdrawal_refresh_decision")
        if _has_daily_boolean(decision):
            return StepOutcome(WorkflowStatus.ALREADY_DONE, "今天已经决定过是否更新提现信息")
        probability = max(
            0.0,
            min(1.0, float(context.option("withdrawal_refresh_probability", 0.5))),
        )
        selected = context.random.random() < probability
        context.mark_daily("withdrawal_refresh_decision", selected)
        if not selected:
            return StepOutcome.skipped("今天未抽中提现信息更新")
        if context.ocr is None:
            return self._unavailable(context, "提现信息需要 OCR，但当前没有可用 OCR 引擎")
        if not self.go_task_page(context):
            return self._unavailable(context, "更新提现信息时无法进入任务页")

        opened = 0
        for entry in spec.entry_sequence:
            if not context.actions.tap_target(entry, timeout=2.0):
                self._close(context, opened)
                return self._unavailable(context, f"没有找到提现页面入口: {entry.target_id}")
            opened += 1
            context.timing.wait(
                context.sample_seconds(
                    "withdrawal_page_wait_seconds",
                    max(1.0, spec.page_wait_seconds * 0.6),
                    max(1.0, spec.page_wait_seconds * 1.4),
                    default_center=spec.page_wait_seconds,
                )
            )

        for popup in spec.dismiss_popups:
            if popup.marker is not None and not context.actions.exists(popup.marker, timeout=1.0):
                continue
            if context.actions.tap_target(popup.close_target, timeout=1.0):
                context.timing.operation_delay()
        observation = context.actions.observe(include_ui_tree=False, include_screenshot=True)
        if observation is None or observation.screenshot is None:
            self._close(context, spec.close_back_count)
            return self._unavailable(context, "提现页面截图失败")
        try:
            texts = context.ocr.recognize(observation.screenshot)
        except Exception as error:
            self._close(context, spec.close_back_count)
            return self._unavailable(context, f"提现页面 OCR 失败: {error}")

        available = _first_amount_in_region(texts, spec.available_region, spec.scale)
        tiers, notes = _withdrawal_details(
            texts,
            spec.details_region or spec.minimum_region,
            spec.available_region,
            available,
            spec.scale,
            spec.max_tiers,
        )
        minimum = spec.minimum_amount_minor
        if spec.minimum_region is not None:
            detected = _minimum_amount_in_region(texts, spec.minimum_region, spec.scale)
            if detected is not None:
                minimum = detected
        if tiers:
            minimum = min(item["amount_minor"] for item in tiers)
        if available is None:
            self._close(context, spec.close_back_count)
            return self._unavailable(context, "没有识别到可提现余额")

        eligible = minimum is not None and available >= minimum
        data = {
            "business_date": context.business_date.isoformat(),
            "available_amount_minor": available,
            "minimum_amount_minor": minimum,
            "scale": spec.scale,
            "unit": spec.unit,
            "eligible": eligible,
            "tiers": tiers,
            "notes": notes,
        }
        context.state.set(
            context.namespace,
            "withdrawal:last",
            {**data, "captured_at": context.timing.clock.now().isoformat()},
        )
        summary = f"可提现 {_format_minor(available, spec.scale)}{spec.unit}"
        if minimum is not None:
            summary += f"，门槛 {_format_minor(minimum, spec.scale)}{spec.unit}"
        if tiers:
            summary += f"，已识别 {len(tiers)} 个档位"
        context.emit(
            "reward.withdrawal.snapshot",
            "提现信息更新",
            summary,
            workflow_id="daily",
            step_id="更新提现信息",
            status="success",
            data=data,
        )
        self._close(context, spec.close_back_count)
        return StepOutcome.success("提现信息更新完成", **data)

    @staticmethod
    def _unavailable(context: AppContext, message: str) -> StepOutcome:
        context.emit(
            "reward.withdrawal.unavailable",
            "提现信息暂不可用",
            message,
            level=EventLevel.WARNING,
            workflow_id="daily",
            step_id="更新提现信息",
            status="skipped",
        )
        return StepOutcome.skipped(message)

    @staticmethod
    def _is_fresh(context: AppContext, spec: WithdrawalSpec) -> bool:
        value = context.state.get(context.namespace, "withdrawal:last", {})
        if not isinstance(value, dict):
            return False
        try:
            captured_date = date.fromisoformat(str(value["business_date"]))
        except (KeyError, TypeError, ValueError):
            return False
        age = (context.business_date - captured_date).days
        return 0 <= age < spec.refresh_days and "tiers" in value and "notes" in value

    @staticmethod
    def _close(context: AppContext, count: int) -> None:
        for _ in range(count):
            context.actions.press(SystemKey.BACK)
            context.timing.operation_delay()


def _first_amount_in_region(texts, region, scale: int) -> int | None:
    items = sorted(
        (item for item in texts if _point_in_region(item.bounds.center, region)),
        key=lambda item: (item.bounds.top, item.bounds.left),
    )
    for item in items:
        amount = _amount_minor(item.text, scale)
        if amount is not None:
            return amount
    return _amount_minor(" ".join(item.text for item in items), scale)


def _minimum_amount_in_region(texts, region, scale: int) -> int | None:
    amounts = {
        amount
        for item in texts
        if _point_in_region(item.bounds.center, region)
        for amount in (_amount_minor(item.text, scale),)
        if amount is not None and amount >= 0
    }
    return min(amounts) if amounts else None


_TIER_AMOUNT = re.compile(r"(?:[¥￥]\s*)?(\d[\d,]*(?:\.\d+)?)\s*元")
_REQUIREMENT_WORDS = re.compile(
    r"需|须|满|连续|签到|天|次|新人|新用户|限|邀请|审核|到账|实名|银行卡|条件|要求"
)
_GENERIC_WITHDRAWAL_TEXT = re.compile(r"^(?:立即)?(?:去)?提现$|^选择$|^可提现$")


def _withdrawal_details(
    texts,
    region,
    available_region,
    available: int | None,
    scale: int,
    max_tiers: int,
) -> tuple[list[dict[str, object]], list[str]]:
    if region is None:
        return [], []
    items = sorted(
        (
            item
            for item in texts
            if _point_in_region(item.bounds.center, region)
            and not _point_in_region(item.bounds.center, available_region)
        ),
        key=lambda item: (item.bounds.top, item.bounds.left),
    )
    amount_items: list[tuple[object, int]] = []
    seen_amounts: set[int] = set()
    for item in items:
        match = _TIER_AMOUNT.search(_clean_ocr_text(item.text))
        amount = _amount_minor(match.group(1), scale) if match is not None else None
        if amount is None or amount < 0 or amount in seen_amounts:
            continue
        seen_amounts.add(amount)
        amount_items.append((item, amount))
    amount_items = sorted(amount_items, key=lambda pair: pair[1])[:max_tiers]

    assigned_ids: set[int] = set()
    tiers: list[dict[str, object]] = []
    amount_item_ids = {id(item) for item, _ in amount_items}
    for amount_item, amount in amount_items:
        requirement_parts: list[str] = []
        for item in items:
            if id(item) in amount_item_ids:
                continue
            text = _clean_ocr_text(item.text)
            if not text or _GENERIC_WITHDRAWAL_TEXT.fullmatch(text):
                continue
            center = item.bounds.center
            amount_center = amount_item.bounds.center
            nearest = min(
                amount_items,
                key=lambda pair: abs(pair[0].bounds.center.x - center.x),
            )[0]
            if nearest is not amount_item:
                continue
            if not amount_item.bounds.top - 0.03 <= center.y <= amount_item.bounds.bottom + 0.20:
                continue
            requirement_parts.append(text)
            assigned_ids.add(id(item))
        requirement = _join_detail_text(requirement_parts)
        tiers.append(
            {
                "amount_minor": amount,
                "balance_eligible": available is not None and available >= amount,
                "requirement": requirement,
            }
        )

    notes = []
    for item in items:
        if id(item) in amount_item_ids or id(item) in assigned_ids:
            continue
        text = _clean_ocr_text(item.text)
        if text and _REQUIREMENT_WORDS.search(text):
            notes.append(text)
    return tiers, _unique_texts(notes, limit=3)


def _clean_ocr_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()[:120]


def _join_detail_text(values: Sequence[str]) -> str:
    return " · ".join(_unique_texts(values, limit=3))[:240]


def _unique_texts(values: Sequence[str], *, limit: int) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
        if len(result) >= limit:
            break
    return result


def _point_in_region(point, region) -> bool:
    return region.left <= point.x <= region.right and region.top <= point.y <= region.bottom


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
            return _optional_reward_unavailable(
                context,
                "领取时段奖励",
                "领取时段奖励时无法进入任务页",
            )
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
        if spec.success_target is not None:
            context.record_reward(
                "duration_reward",
                "时段奖励已确认到账",
                workflow_id="daily",
                step_id="领取时段奖励",
                evidence_target_id=spec.success_target.target_id,
            )
        ad_outcome: StepOutcome | None = None
        if spec.ad_target is not None and self.app_spec.ad is not None:
            if context.actions.tap_target(spec.ad_target, timeout=1.0):
                ad_outcome = AdStateMachine().run(context, self.app_spec.ad)
        if spec.close_target is not None:
            context.actions.tap_target(spec.close_target, timeout=1.0)
        if ad_outcome is not None and ad_outcome.status is not WorkflowStatus.SUCCESS:
            context.emit(
                "reward.duration.extra_ad.unavailable",
                "附加广告暂不可用",
                ad_outcome.message,
                level=EventLevel.WARNING,
                workflow_id="daily",
                step_id="领取时段奖励",
                status="skipped",
            )
            return StepOutcome.success(
                "时段奖励已领取，附加广告未完整结束",
                ad_status=ad_outcome.status.value,
                ad_message=ad_outcome.message,
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
        return self._summarize(completed, uncertain, failed, total)

    @staticmethod
    def _summarize(completed: int, uncertain: int, failed: int, total: int) -> StepOutcome:
        outputs = {
            "completed": completed,
            "uncertain": uncertain,
            "failed": failed,
            "total": total,
        }
        if completed > 0:
            return StepOutcome.success("可用广告奖励领取完成", **outputs)
        if uncertain > 0:
            return StepOutcome(
                WorkflowStatus.PARTIAL,
                "广告任务结果未能完全确认",
                outputs,
            )
        return StepOutcome(WorkflowStatus.SKIPPED, "当前没有可领取的广告奖励", outputs)

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
