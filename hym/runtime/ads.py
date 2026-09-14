from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from hym.apps.specs import AdSpec
from hym.core.events import EventLevel
from hym.core.models import SystemKey, WorkflowStatus
from hym.runtime.context import AppContext
from hym.runtime.workflow import StepOutcome


@dataclass(slots=True)
class AdStateMachine:
    """用有界循环处理普通广告、连续广告和广告落地页。"""

    def run(self, context: AppContext, spec: AdSpec) -> StepOutcome:
        actions = context.actions
        page_targets = (
            *spec.start_markers,
            *spec.completion_markers,
            *spec.exit_prompt_markers,
            *spec.exit_prompt_continue_targets,
            *spec.exit_prompt_close_targets,
            *spec.exit_targets,
        )
        needs_screenshot = actions.needs_screenshot(page_targets)
        entered = None
        for _ in range(spec.entry_attempts):
            entered = actions.resolve_many(spec.start_markers, include_screenshot=needs_screenshot)
            if entered is not None:
                break
            context.timing.operation_delay()
        if entered is None:
            return StepOutcome.failure("没有识别到广告播放页")

        stage_waited = False
        back_attempts = 0
        progress_count = 0
        ad_stage = 0
        wait_count = 0
        extra_round_limit = _extra_round_limit(context, spec)
        extra_rounds_started = 0
        if spec.exit_prompt_continue_targets:
            context.emit(
                "ad.extra.plan.created",
                "广告追加计划",
                f"本次广告最多追加观看 {extra_round_limit} 轮",
                workflow_id="daily",
                step_id="ad",
                status="running",
                data={"extra_round_limit": extra_round_limit},
            )

        for cycle in range(1, spec.max_cycles + 1):
            context.emit(
                "ad.state.changed",
                "广告状态变化",
                f"正在处理广告，第 {cycle} 轮",
                level=EventLevel.DEBUG,
                workflow_id="daily",
                step_id="ad",
                status="running",
                data={"cycle": cycle},
            )
            observation = actions.observe(include_ui_tree=True, include_screenshot=needs_screenshot)
            if observation is None:
                continue

            # 退出确认弹窗可能覆盖在广告页上，必须先于底层倒计时处理。
            prompt_match = _first_match(actions, spec.exit_prompt_markers, observation)
            if prompt_match is not None:
                if extra_rounds_started < extra_round_limit:
                    clicked = actions.tap_first(spec.exit_prompt_continue_targets, timeout=1.0)
                    if clicked is not None:
                        extra_rounds_started += 1
                        ad_stage += 1
                        stage_waited = False
                        progress_count += 1
                        context.emit(
                            "ad.extra.started",
                            "广告追加观看",
                            f"开始追加观看第 {extra_rounds_started}/{extra_round_limit} 轮奖励广告",
                            workflow_id="daily",
                            step_id="ad",
                            status="running",
                            data={
                                "extra_round": extra_rounds_started,
                                "extra_round_limit": extra_round_limit,
                            },
                        )
                        context.timing.operation_delay()
                        continue
                clicked = actions.tap_first(spec.exit_prompt_close_targets, timeout=1.0)
                if clicked is not None:
                    progress_count += 1
                    context.emit(
                        "ad.exit.prompt.closed",
                        "广告退出弹窗已关闭",
                        "已关闭广告退出确认弹窗",
                        workflow_id="daily",
                        step_id="ad",
                        status="success",
                        data={
                            "cycle": cycle,
                            "stage": ad_stage + 1,
                            "extra_rounds_started": extra_rounds_started,
                        },
                    )
                    context.timing.operation_delay()
                    continue

            start_match = _first_match(actions, spec.start_markers, observation)
            if start_match is None and _matches_any(actions, spec.exit_targets, observation):
                return StepOutcome.success(
                    "广告流程已结束",
                    cycles=cycle,
                    progress_count=progress_count,
                    wait_count=wait_count,
                )

            if start_match is not None and not stage_waited:
                matched_target, resolved = start_match
                context.emit(
                    "ad.wait.started",
                    "广告等待开始",
                    "已识别广告播放页，开始等待本轮奖励",
                    workflow_id="daily",
                    step_id="ad",
                    status="running",
                    data={
                        "cycle": cycle,
                        "stage": ad_stage + 1,
                        "target_id": matched_target.target_id,
                        "strategy_id": resolved.target.strategy_id if resolved.target else None,
                        "fallback_seconds": float(
                            context.option(
                                "ad_fallback_wait_seconds",
                                spec.completion_wait_seconds,
                            )
                        ),
                    },
                )
                wait_result = _wait_for_completion(context, spec)
                stage_waited = True
                wait_count += 1
                progress_count += 1
                if wait_result.target_id is not None:
                    context.emit(
                        "ad.completion.detected",
                        "广告完成信号命中",
                        f"已通过 {wait_result.target_id} 确认本轮广告结束",
                        workflow_id="daily",
                        step_id="ad",
                        status="success",
                        data={
                            "cycle": cycle,
                            "stage": ad_stage + 1,
                            "target_id": wait_result.target_id,
                            "strategy_id": wait_result.strategy_id,
                            "detected_after_seconds": round(
                                wait_result.detected_after_seconds or 0.0,
                                2,
                            ),
                            "settle_seconds": round(wait_result.settle_seconds, 2),
                        },
                    )
                context.emit(
                    "ad.wait.finished",
                    "广告等待完成",
                    (
                        "检测到广告完成，本轮随机停留结束"
                        if wait_result.target_id is not None
                        else "未检测到明确完成信号，已等待到兜底时间"
                    ),
                    workflow_id="daily",
                    step_id="ad",
                    status="success",
                    data={
                        "cycle": cycle,
                        "stage": ad_stage + 1,
                        "wait_index": wait_count,
                        "waited_seconds": round(wait_result.waited_seconds, 2),
                        "completion_detected": wait_result.target_id is not None,
                        "completion_target_id": wait_result.target_id,
                    },
                )
                if spec.exit_after_wait_with_back:
                    pressed = actions.press(SystemKey.BACK)
                    context.emit(
                        "ad.exit.requested",
                        "请求退出广告",
                        "广告已完成一轮，返回并等待退出确认弹窗",
                        workflow_id="daily",
                        step_id="ad",
                        status="success" if pressed else "failed",
                        data={"cycle": cycle, "stage": ad_stage + 1},
                    )
                    context.timing.operation_delay()
                    continue

            clicked = actions.tap_first(spec.continue_targets, timeout=0.5)
            if clicked is not None:
                progress_count += 1
                context.timing.operation_delay()
                continue

            sequence_completed = False
            for sequence in spec.next_sequences:
                first = sequence[0] if sequence else None
                if first is None or not actions.exists(first, timeout=0.5):
                    continue
                sequence_completed = all(actions.tap_target(target, timeout=1.5) for target in sequence)
                if sequence_completed:
                    progress_count += 1
                    ad_stage += 1
                    stage_waited = False
                    context.timing.operation_delay()
                    break
            if sequence_completed:
                continue

            clicked = actions.tap_first(spec.close_targets, timeout=0.6)
            if clicked is not None:
                progress_count += 1
                context.timing.operation_delay()
                continue

            if back_attempts < spec.max_back_attempts:
                actions.press(SystemKey.BACK)
                back_attempts += 1
                context.timing.operation_delay()
                continue
            break

        for _ in range(spec.max_back_attempts):
            if actions.tap_first(spec.final_close_targets, timeout=0.5) is None:
                if _matches_current_page(context, spec.exit_targets):
                    break
                actions.press(SystemKey.BACK)
            context.timing.operation_delay()

        if _matches_current_page(context, spec.exit_targets):
            return StepOutcome(
                WorkflowStatus.PARTIAL,
                "广告流程通过恢复动作退出",
                {"progress_count": progress_count},
            )
        context.emit(
            "ad.recovery.required",
            "广告恢复处理",
            "广告页未正常退出，将返回首页后继续其他流程",
            level=EventLevel.WARNING,
            workflow_id="daily",
            step_id="ad",
            status="failed",
        )
        return StepOutcome.failure("广告流程达到处理上限")


def _first_match(actions, targets, observation):
    for target in targets:
        result = actions.resolve_in(target, observation)
        if result.found:
            return target, result
    return None


def _matches_any(actions, targets, observation) -> bool:
    return _first_match(actions, targets, observation) is not None


def _matches_current_page(context: AppContext, targets) -> bool:
    return context.actions.resolve_many(targets, include_screenshot=False) is not None


def _extra_round_limit(context: AppContext, spec: AdSpec) -> int:
    if not spec.exit_prompt_continue_targets:
        return 0
    minimum = max(0, int(context.option("ad_extra_rounds_min", spec.extra_rounds_min)))
    maximum = max(minimum, int(context.option("ad_extra_rounds_max", spec.extra_rounds_max)))
    return context.sample_count(
        "ad_extra_rounds",
        minimum,
        maximum,
    )


@dataclass(frozen=True, slots=True)
class _CompletionWaitResult:
    waited_seconds: float
    target_id: str | None = None
    strategy_id: str | None = None
    detected_after_seconds: float | None = None
    settle_seconds: float = 0.0


def _wait_for_completion(context: AppContext, spec: AdSpec) -> _CompletionWaitResult:
    """低频检查可靠完成信号；没有信号时保留原奖励等待兜底。"""

    fallback_seconds = float(
        context.option("ad_fallback_wait_seconds", spec.completion_wait_seconds)
    )
    budget = context.timing.baseline_seconds(fallback_seconds, reward_wait=True)
    if not spec.completion_markers:
        context.timing.clock.sleep(budget)
        return _CompletionWaitResult(budget)

    interval_min = max(
        1.0,
        float(
            context.option(
                "ad_completion_check_interval_seconds_min",
                spec.completion_check_interval_seconds_min,
            )
        ),
    )
    interval_max = max(
        interval_min,
        float(
            context.option(
                "ad_completion_check_interval_seconds_max",
                spec.completion_check_interval_seconds_max,
            )
        ),
    )
    interval_center, interval_stddev = _distribution_parameters(
        context,
        "ad_completion_check_interval_seconds",
        interval_min,
        interval_max,
        spec.completion_check_interval_seconds_min,
        spec.completion_check_interval_seconds_max,
        spec.completion_check_interval_seconds_center,
        spec.completion_check_interval_seconds_stddev,
    )
    settle_min = max(
        0.0,
        float(
            context.option(
                "ad_completion_settle_seconds_min",
                spec.completion_settle_seconds_min,
            )
        ),
    )
    settle_max = max(
        settle_min,
        float(
            context.option(
                "ad_completion_settle_seconds_max",
                spec.completion_settle_seconds_max,
            )
        ),
    )
    settle_center, settle_stddev = _distribution_parameters(
        context,
        "ad_completion_settle_seconds",
        settle_min,
        settle_max,
        spec.completion_settle_seconds_min,
        spec.completion_settle_seconds_max,
        spec.completion_settle_seconds_center,
        spec.completion_settle_seconds_stddev,
    )
    started = context.timing.clock.now()
    deadline = started + timedelta(seconds=budget)
    needs_screenshot = context.actions.needs_screenshot(spec.completion_markers)

    while context.timing.clock.now() < deadline:
        remaining = max(
            0.0,
            (deadline - context.timing.clock.now()).total_seconds(),
        )
        interval = min(
            remaining,
            context.timing.range_seconds(
                interval_min,
                interval_max,
                center=interval_center,
                stddev=interval_stddev,
            ),
        )
        if interval > 0:
            context.timing.clock.sleep(interval)
        if context.timing.clock.now() >= deadline:
            break
        matched = context.actions.resolve_many(
            spec.completion_markers,
            include_screenshot=needs_screenshot,
        )
        if matched is None:
            continue
        target, resolved = matched
        detected_after = max(
            0.0,
            (context.timing.clock.now() - started).total_seconds(),
        )
        settle_seconds = (
            context.timing.range_seconds(
                settle_min,
                settle_max,
                center=settle_center,
                stddev=settle_stddev,
            )
            if settle_max > 0
            else 0.0
        )
        if settle_seconds > 0:
            context.timing.clock.sleep(settle_seconds)
        return _CompletionWaitResult(
            waited_seconds=max(
                0.0,
                (context.timing.clock.now() - started).total_seconds(),
            ),
            target_id=target.target_id,
            strategy_id=resolved.target.strategy_id if resolved.target else None,
            detected_after_seconds=detected_after,
            settle_seconds=settle_seconds,
        )

    return _CompletionWaitResult(
        waited_seconds=max(
            0.0,
            (context.timing.clock.now() - started).total_seconds(),
        )
    )


def _distribution_parameters(
    context: AppContext,
    prefix: str,
    minimum: float,
    maximum: float,
    default_minimum: float,
    default_maximum: float,
    default_center: float,
    default_stddev: float,
) -> tuple[float, float]:
    sentinel = object()
    configured_center = context.option(f"{prefix}_center", sentinel)
    configured_stddev = context.option(f"{prefix}_stddev", sentinel)
    bounds_changed = minimum != default_minimum or maximum != default_maximum
    center = (
        (minimum + maximum) / 2
        if configured_center is sentinel and bounds_changed
        else default_center if configured_center is sentinel else float(configured_center)
    )
    stddev = (
        max((maximum - minimum) / 6, 0.001)
        if configured_stddev is sentinel and bounds_changed
        else default_stddev if configured_stddev is sentinel else float(configured_stddev)
    )
    return center, stddev
