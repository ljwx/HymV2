from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import re
from typing import Sequence

from hym.core.events import EventLevel
from hym.core.models import Observation, ObservationRequest, Point, SwipeGesture, SystemKey, UiTreeSource
from hym.core.ports import LocatorPort
from hym.core.pages import PageMatchResult, PageMatchStatus, PageSpec
from hym.core.targets import LocatorKind, ResolveResult, ResolveStatus, ResolvedTarget, TargetSpec
from hym.runtime.context import AppContext

_VISION_KINDS = {LocatorKind.OCR_TEXT, LocatorKind.IMAGE}
_UI_KINDS = {
    LocatorKind.UI_ID,
    LocatorKind.UI_TEXT,
    LocatorKind.UI_DESC,
    LocatorKind.UI_REGEX,
    LocatorKind.UI_QUERY,
}


class ActionController:
    """把观察、定位、点击和必要日志收敛到一个入口。"""

    def __init__(self, context: AppContext, locator: LocatorPort) -> None:
        self.context = context
        self.locator = locator

    def resolve(self, target: TargetSpec, timeout: float = 2.0) -> ResolveResult:
        deadline = self.context.timing.clock.now() + timedelta(seconds=max(0.0, timeout))
        latest = ResolveResult(ResolveStatus.NOT_FOUND, message="尚未观察页面")
        primary, fallback = _locator_stages(target, self.locator)
        tree_source = _tree_source((target,), self.context.observation_profile.ui_tree_source)
        while True:
            if primary is not None:
                observation = self.observe(
                    include_ui_tree=_needs_ui_tree((primary,)),
                    include_screenshot=False,
                    ui_tree_source=tree_source,
                )
                if observation is not None:
                    latest = self.locator.resolve(primary, observation)
                    self.context.record_locator_result(target.target_id, latest)
                    if latest.found:
                        self._log_resolution(target, latest)
                        return latest

            if fallback is not None:
                observation = self.observe(
                    include_ui_tree=_needs_ui_tree((fallback,)),
                    include_screenshot=True,
                    ui_tree_source=tree_source,
                )
                if observation is not None:
                    fallback_result = self.locator.resolve(fallback, observation)
                    latest = _combine_results(latest, fallback_result)
                    self.context.record_locator_result(target.target_id, latest)
                    if latest.found:
                        self._log_resolution(target, latest)
                        return latest

            if self.context.timing.clock.now() >= deadline:
                return latest
            self.context.timing.clock.sleep(min(0.4, max(0.0, (deadline - self.context.timing.clock.now()).total_seconds())))

    def resolve_many(
        self,
        targets: Sequence[TargetSpec],
        *,
        include_screenshot: bool = False,
        include_ui_tree: bool | None = None,
        screenshot_max_size: int | None = None,
    ) -> tuple[TargetSpec, ResolveResult] | None:
        observation = self.observe(
            include_ui_tree=(
                _needs_ui_tree(targets)
                if include_ui_tree is None
                else include_ui_tree
            ),
            include_screenshot=include_screenshot,
            ui_tree_source=_tree_source(targets, self.context.observation_profile.ui_tree_source),
            screenshot_max_size=screenshot_max_size,
        )
        if observation is None:
            return None
        for target in targets:
            result = self.locator.resolve(target, observation)
            self.context.record_locator_result(target.target_id, result)
            if result.found:
                self._log_resolution(target, result)
                return target, result
        return None

    def resolve_in(self, target: TargetSpec, observation: Observation) -> ResolveResult:
        result = self.locator.resolve(target, observation)
        self.context.record_locator_result(target.target_id, result)
        if result.found:
            self._log_resolution(target, result)
        return result

    def match_page(
        self,
        page: PageSpec,
        *,
        observation: Observation | None = None,
        extra_targets: Sequence[TargetSpec] = (),
        visual_fallback: bool = True,
    ) -> PageMatchResult:
        """先用包名、Activity 和 UI 信号判断，必要时再补一次视觉观察。"""

        targets = (*page.markers, *page.forbidden_markers, *extra_targets)
        profile = page.observation_profile or self.context.observation_profile
        current = observation or self.observe(
            include_ui_tree=_needs_ui_tree(targets),
            include_screenshot=False,
            ui_tree_source=profile.ui_tree_source,
            screenshot_max_size=profile.screenshot_max_size,
        )
        if current is None:
            return PageMatchResult(
                page.page_id,
                PageMatchStatus.OBSERVATION_FAILED,
                message="页面观察失败",
            )

        result = self._match_page_in(page, current)
        if (
            result.matched
            or result.message.startswith("前台包名不符")
            or result.message.startswith("Activity 不符")
            or not visual_fallback
            or current.screenshot is not None
            or not self.needs_screenshot((*page.markers, *page.forbidden_markers))
        ):
            return result

        visual = self.observe(
            include_ui_tree=_needs_ui_tree(targets),
            include_screenshot=True,
            ui_tree_source=profile.ui_tree_source,
            screenshot_max_size=profile.screenshot_max_size,
        )
        if visual is None:
            return result
        return self._match_page_in(page, visual)

    def _match_page_in(self, page: PageSpec, observation: Observation) -> PageMatchResult:
        activity = observation.activity
        if activity.package_name != page.package_name:
            return PageMatchResult(
                page.page_id,
                PageMatchStatus.NOT_MATCHED,
                observation,
                message=f"前台包名不符: {activity.package_name or '未知'}",
            )
        if page.activity_patterns and not any(
            re.search(pattern, activity.activity_name or "") for pattern in page.activity_patterns
        ):
            return PageMatchResult(
                page.page_id,
                PageMatchStatus.NOT_MATCHED,
                observation,
                message=f"Activity 不符: {activity.activity_name or '未知'}",
            )

        forbidden = tuple(
            target.target_id
            for target in page.forbidden_markers
            if self.resolve_in(target, observation).found
        )
        if forbidden:
            return PageMatchResult(
                page.page_id,
                PageMatchStatus.NOT_MATCHED,
                observation,
                forbidden_markers=forbidden,
                message="命中页面排除信号",
            )
        matched = tuple(
            target.target_id for target in page.markers if self.resolve_in(target, observation).found
        )
        status = (
            PageMatchStatus.MATCHED
            if len(matched) >= page.minimum_markers
            else PageMatchStatus.NOT_MATCHED
        )
        return PageMatchResult(
            page.page_id,
            status,
            observation,
            matched_markers=matched,
            message=(
                "页面识别成功"
                if status is PageMatchStatus.MATCHED
                else f"页面信号不足: {len(matched)}/{page.minimum_markers}"
            ),
        )

    def needs_screenshot(self, targets: Sequence[TargetSpec]) -> bool:
        """仅在定位链确实启用了视觉能力时采集截图。"""

        return any(
            locator.kind in _VISION_KINDS and _locator_supported(self.locator, locator.kind)
            for target in targets
            for locator in target.locators
        )

    def tap_first(self, targets: Sequence[TargetSpec], *, timeout: float = 1.0) -> str | None:
        if not targets:
            return None
        deadline = self.context.timing.clock.now() + timedelta(seconds=max(0.0, timeout))
        while True:
            resolved = self.resolve_many(
                targets,
                include_screenshot=self.needs_screenshot(targets),
            )
            if resolved is not None:
                target, result = resolved
                if result.target is not None and self.tap_resolved(result.target):
                    return target.target_id
            if self.context.timing.clock.now() >= deadline:
                return None
            self.context.timing.clock.sleep(0.3)

    def tap_resolved(self, target: ResolvedTarget) -> bool:
        point = self._touch_point(target)
        return self.context.session.tap(point, self.context.timing.touch_duration()).succeeded

    def exists(self, target: TargetSpec, timeout: float = 1.0) -> bool:
        return self.resolve(target, timeout).found

    def tap_target(self, target: TargetSpec, timeout: float = 2.0) -> bool:
        result = self.resolve(target, timeout)
        if not result.found or result.target is None:
            if target.required:
                self.context.emit(
                    "locator.not_found",
                    "目标定位失败",
                    f"未找到必要目标: {target.target_id}",
                    level=EventLevel.WARNING,
                    status="failed",
                    data={
                        "target_id": target.target_id,
                        "attempts": [
                            {
                                "strategy_id": attempt.strategy_id,
                                "status": attempt.status.value,
                                "elapsed_seconds": round(attempt.elapsed_seconds, 4),
                                "message": attempt.message,
                            }
                            for attempt in result.attempts
                        ],
                    },
                )
            return False
        point = self._touch_point(result.target)
        action = self.context.session.tap(point, self.context.timing.touch_duration())
        self.context.emit(
            "action.tap.finished",
            "点击动作完成",
            f"点击目标: {target.target_id}",
            level=EventLevel.DEBUG,
            status=action.status.value,
            data={
                "target_id": target.target_id,
                "strategy_id": result.target.strategy_id,
                "confidence": result.target.confidence,
            },
        )
        return action.succeeded

    def observe_for(
        self,
        targets: Sequence[TargetSpec],
        *,
        include_screenshot: bool,
    ) -> Observation | None:
        return self.observe(
            include_ui_tree=_needs_ui_tree(targets),
            include_screenshot=include_screenshot,
            ui_tree_source=_tree_source(targets, self.context.observation_profile.ui_tree_source),
        )

    def observe(
        self,
        *,
        include_ui_tree: bool,
        include_screenshot: bool,
        ui_tree_source: UiTreeSource = UiTreeSource.AUTO,
        screenshot_max_size: int | None = None,
    ) -> Observation | None:
        if ui_tree_source is UiTreeSource.AUTO:
            ui_tree_source = self.context.observation_profile.ui_tree_source
        if screenshot_max_size is None:
            screenshot_max_size = self.context.observation_profile.screenshot_max_size
        result = self.context.session.observe(
            ObservationRequest(
                include_ui_tree=include_ui_tree,
                include_screenshot=include_screenshot,
                screenshot_max_size=screenshot_max_size,
                ui_tree_source=ui_tree_source,
            )
        )
        if result.succeeded:
            return result.observation
        self.context.emit(
            "observation.failed",
            "页面观察失败",
            f"页面观察失败: {result.message or '未知原因'}",
            level=EventLevel.WARNING,
            status=result.status.value,
        )
        return None

    def press(self, key: SystemKey) -> bool:
        return self.context.session.press(key).succeeded

    def input_text(self, value: str) -> bool:
        if not value:
            return False
        action = self.context.session.input_text(value)
        self.context.emit(
            "action.text_input.finished",
            "文本输入完成",
            "文本已写入当前输入框" if action.succeeded else "文本输入失败",
            level=EventLevel.DEBUG if action.succeeded else EventLevel.WARNING,
            status=action.status.value,
            # 只记录长度，避免好友消息进入日志或后续上报数据。
            data={"text_length": len(value)},
        )
        return action.succeeded

    def swipe_up(self) -> bool:
        settings = self.context.timing.settings
        x = self.context.random.uniform(settings.swipe_x_min, settings.swipe_x_max)
        gesture = SwipeGesture(
            Point(x, self.context.random.uniform(settings.swipe_up_start_min, settings.swipe_up_start_max)),
            Point(x, self.context.random.uniform(settings.swipe_up_end_min, settings.swipe_up_end_max)),
            self.context.timing.swipe_duration(),
        )
        return self.context.session.swipe(gesture).succeeded

    def swipe_down(self) -> bool:
        settings = self.context.timing.settings
        x = self.context.random.uniform(settings.swipe_x_min, settings.swipe_x_max)
        gesture = SwipeGesture(
            Point(x, self.context.random.uniform(settings.swipe_up_end_min, settings.swipe_up_end_max)),
            Point(x, self.context.random.uniform(settings.swipe_up_start_min, settings.swipe_up_start_max)),
            self.context.timing.swipe_duration(),
        )
        return self.context.session.swipe(gesture).succeeded

    def _touch_point(self, target: ResolvedTarget) -> Point:
        offset = self.context.timing.settings.touch_offset_ratio
        if offset <= 0:
            return target.point
        if target.bounds is not None:
            offset = min(
                offset,
                (target.bounds.right - target.bounds.left) * 0.2,
                (target.bounds.bottom - target.bounds.top) * 0.2,
            )
        return Point(
            min(1.0, max(0.0, target.point.x + self.context.random.uniform(-offset, offset))),
            min(1.0, max(0.0, target.point.y + self.context.random.uniform(-offset, offset))),
        )

    def _log_resolution(self, target: TargetSpec, result: ResolveResult) -> None:
        if result.target is None:
            return
        first_strategy = min(target.locators, key=lambda item: item.priority).strategy_id
        if result.target.strategy_id != first_strategy:
            self.context.emit(
                "locator.fallback.succeeded",
                "降级定位成功",
                f"目标 {target.target_id} 使用备用策略定位成功",
                level=EventLevel.DEBUG,
                workflow_id=None,
                status="success",
                data={
                    "target_id": target.target_id,
                    "strategy_id": result.target.strategy_id,
                    "confidence": result.target.confidence,
                },
            )


def _locator_stages(target: TargetSpec, resolver: LocatorPort) -> tuple[TargetSpec | None, TargetSpec | None]:
    supported_vision = tuple(
        locator
        for locator in target.locators
        if locator.kind in _VISION_KINDS and _locator_supported(resolver, locator.kind)
    )
    if not supported_vision:
        locators = tuple(locator for locator in target.locators if locator.kind not in _VISION_KINDS)
        return (replace(target, locators=locators) if locators else None), None

    first_vision_priority = min(locator.priority for locator in supported_vision)
    primary_locators = tuple(
        locator
        for locator in target.locators
        if locator.kind not in _VISION_KINDS and locator.priority < first_vision_priority
    )
    fallback_locators = tuple(
        locator
        for locator in target.locators
        if (
            locator.kind in _VISION_KINDS
            and _locator_supported(resolver, locator.kind)
            or locator.kind not in _VISION_KINDS
            and locator.priority >= first_vision_priority
        )
    )
    primary = replace(target, locators=primary_locators) if primary_locators else None
    fallback = replace(target, locators=fallback_locators) if fallback_locators else None
    return primary, fallback


def _combine_results(first: ResolveResult, second: ResolveResult) -> ResolveResult:
    if second.found:
        return ResolveResult(second.status, second.target, first.attempts + second.attempts, second.message)
    return ResolveResult(ResolveStatus.NOT_FOUND, attempts=first.attempts + second.attempts, message=second.message)


def _locator_supported(resolver: LocatorPort, kind: LocatorKind) -> bool:
    supports = getattr(resolver, "supports", None)
    return bool(supports(kind)) if callable(supports) else True


def _tree_source(
    targets: Sequence[TargetSpec],
    default: UiTreeSource = UiTreeSource.AUTO,
) -> UiTreeSource:
    requested: set[UiTreeSource] = set()
    for target in targets:
        value = target.metadata.get("ui_tree_source")
        if value is None:
            continue
        requested.add(value if isinstance(value, UiTreeSource) else UiTreeSource(str(value)))
    if UiTreeSource.ACCESSIBILITY in requested:
        return UiTreeSource.ACCESSIBILITY
    if UiTreeSource.INSTRUMENTATION in requested:
        return UiTreeSource.INSTRUMENTATION
    return default


def _needs_ui_tree(targets: Sequence[TargetSpec]) -> bool:
    return any(locator.kind in _UI_KINDS for target in targets for locator in target.locators)
