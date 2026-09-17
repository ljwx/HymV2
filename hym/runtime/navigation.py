from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from hym.apps.specs import AppSpec, PopupDismissSpec
from hym.core.events import EventLevel
from hym.core.models import Observation, SystemKey
from hym.core.pages import PageSpec
from hym.core.targets import TargetSpec
from hym.runtime.context import AppContext


@dataclass(frozen=True, slots=True)
class NavigationController:
    """根据 App 导航规格完成页面进入和有限恢复。"""

    spec: AppSpec

    def dismiss_launch(self, context: AppContext) -> int:
        navigation = self.spec.navigation
        targets = [*navigation.launch_dismiss]
        for popup in navigation.launch_intercepts:
            targets.append(popup.close_target)
            if popup.marker is not None:
                targets.append(popup.marker)

        closed = 0
        # 最多处理两层连续弹窗，正常启动只观察一次。
        for _ in range(2):
            observation = context.actions.observe_for(targets, include_screenshot=False)
            if observation is None:
                break
            target_id = self.tap_first_in(context, navigation.launch_dismiss, observation)
            if target_id is None:
                target_id = self.dismiss_popup_in(
                    context,
                    navigation.launch_intercepts,
                    observation,
                )
            if target_id is None:
                break
            closed += 1
            self.emit_popup_dismissed(context, target_id)
            context.timing.operation_delay()
        return closed

    def go_home(self, context: AppContext, *, select_tab: bool = False) -> bool:
        navigation = self.spec.navigation
        home_page = navigation.home_page or PageSpec(
            f"{self.spec.identity.app_id}.home",
            self.spec.identity.package_name,
            (navigation.home_marker,),
        )
        home_targets = [navigation.home_marker, navigation.home_tab]
        for popup in navigation.home_intercepts:
            home_targets.append(popup.close_target)
            if popup.marker is not None:
                home_targets.append(popup.marker)

        relaunched = False
        hard_restarted = False
        home_tab_attempted = False
        unexpected_activity = ""
        unexpected_activity_count = 0
        logged_transient_activities: set[str] = set()
        for _ in range(navigation.home_attempts):
            page_result = context.actions.match_page(
                home_page,
                extra_targets=home_targets,
                visual_fallback=False,
            )
            observation = page_result.observation
            if self._foreground_left_app(observation):
                if relaunched:
                    return False
                context.emit(
                    "navigation.app.relaunching",
                    "应用导航恢复",
                    f"前台已离开{self.spec.display_name}，重新拉起应用",
                    workflow_id="daily",
                    status="recovering",
                    data={"foreground_package": observation.activity.package_name},
                )
                self.restart_app(context)
                relaunched = True
                continue

            if page_result.message.startswith("Activity 不符") and observation is not None:
                activity_name = observation.activity.activity_name or "未知"
                if any(
                    re.search(pattern, activity_name)
                    for pattern in navigation.transient_activity_patterns
                ):
                    if activity_name not in logged_transient_activities:
                        context.emit(
                            "navigation.activity.waiting",
                            "等待启动页面",
                            f"{self.spec.display_name}仍在启动，等待进入主页面",
                            workflow_id="daily",
                            status="waiting",
                            data={"activity_name": activity_name},
                        )
                        logged_transient_activities.add(activity_name)
                    context.timing.operation_delay()
                    continue
                if activity_name == unexpected_activity:
                    unexpected_activity_count += 1
                else:
                    unexpected_activity = activity_name
                    unexpected_activity_count = 1
                if unexpected_activity_count >= 2:
                    if hard_restarted:
                        return False
                    context.emit(
                        "navigation.activity.stuck",
                        "页面返回受阻",
                        "连续返回仍停留在异常页面，强制重启应用",
                        level=EventLevel.WARNING,
                        workflow_id="daily",
                        status="recovering",
                        data={"activity_name": activity_name},
                    )
                    self.hard_restart_app(context)
                    unexpected_activity_count = 0
                    relaunched = True
                    hard_restarted = True
                    continue
            else:
                unexpected_activity = ""
                unexpected_activity_count = 0

            if page_result.matched and observation is not None:
                # 某些 App 重复点击已选中的首页会切换展示模式。
                if not select_tab or not navigation.reselect_home_tab:
                    return True
                result = context.actions.resolve_in(navigation.home_tab, observation)
                if result.found and result.target is not None:
                    context.actions.tap_resolved(result.target)
                    context.timing.operation_delay()
                    return True
                # 沉浸页可能只保留底栏容器，下一次观察再找标签。
                if context.actions.tap_target(navigation.home_tab, timeout=1.0):
                    context.timing.operation_delay()
                    return True

            if observation is not None:
                target_id = self.dismiss_popup_in(
                    context,
                    navigation.home_intercepts,
                    observation,
                )
                if target_id is not None:
                    self.emit_popup_dismissed(context, target_id)
                    context.timing.operation_delay()
                    continue
                # 任务页常与首页共用 Activity，先点底栏，避免连续返回。
                if not home_tab_attempted:
                    tab_result = context.actions.resolve_in(navigation.home_tab, observation)
                    if tab_result.found and tab_result.target is not None:
                        if context.actions.tap_resolved(tab_result.target):
                            home_tab_attempted = True
                            context.timing.operation_delay()
                            continue
            context.actions.press(SystemKey.BACK)
            context.timing.operation_delay()
        return False

    def go_task_page(self, context: AppContext) -> bool:
        navigation = self.spec.navigation
        if navigation.task_entry is None or navigation.task_marker is None:
            return False
        task_page = navigation.task_page or PageSpec(
            f"{self.spec.identity.app_id}.task",
            self.spec.identity.package_name,
            (navigation.task_marker,),
        )
        current_result = context.actions.match_page(task_page, visual_fallback=False)
        if current_result.matched:
            target_id = context.actions.tap_first(navigation.task_dismiss, timeout=0)
            if target_id is not None:
                self.emit_popup_dismissed(context, target_id)
                context.timing.operation_delay()
            return True
        if not self.go_home(context, select_tab=True):
            return False
        if not context.actions.tap_target(navigation.task_entry, timeout=2.0):
            return False
        context.timing.wait(navigation.page_wait_seconds)
        page_result = context.actions.match_page(
            task_page,
            extra_targets=navigation.task_dismiss,
        )
        observation = page_result.observation
        target_id = None
        if observation is not None:
            target_id = self.tap_first_in(context, navigation.task_dismiss, observation)
            if target_id is not None:
                self.emit_popup_dismissed(context, target_id)
                context.timing.operation_delay()
            elif page_result.matched:
                return True
        # 结构定位失败时才允许图片策略补一次。
        if observation is None or target_id is None:
            fallback_id = context.actions.tap_first(navigation.task_dismiss, timeout=0)
            if fallback_id is not None:
                self.emit_popup_dismissed(context, fallback_id)
                context.timing.operation_delay()
        return context.actions.match_page(task_page).matched

    def recover_home(self, context: AppContext) -> None:
        if self.go_home(context):
            return
        self.hard_restart_app(context)
        self.go_home(context, select_tab=True)

    def restart_app(self, context: AppContext) -> None:
        context.actions.press(SystemKey.HOME)
        context.session.start_app(self.spec.identity)
        context.timing.wait(float(context.option("launch_wait_seconds", 6.0)))

    def hard_restart_app(self, context: AppContext) -> None:
        """只在返回链已确认无效时清理当前任务栈。"""

        context.session.stop_app(self.spec.identity)
        context.timing.operation_delay()
        context.session.start_app(self.spec.identity)
        context.timing.wait(float(context.option("launch_wait_seconds", 6.0)))

    @staticmethod
    def tap_first_in(
        context: AppContext,
        targets: Sequence[TargetSpec],
        observation: Observation,
    ) -> str | None:
        for target in targets:
            result = context.actions.resolve_in(target, observation)
            if not result.found or result.target is None:
                continue
            if context.actions.tap_resolved(result.target):
                return target.target_id
        return None

    @classmethod
    def dismiss_popup_in(
        cls,
        context: AppContext,
        popups: Sequence[PopupDismissSpec],
        observation: Observation,
    ) -> str | None:
        for popup in popups:
            if popup.marker is not None and not context.actions.resolve_in(
                popup.marker,
                observation,
            ).found:
                continue
            target_id = cls.tap_first_in(context, (popup.close_target,), observation)
            if target_id is not None:
                return target_id
        return None

    def emit_popup_dismissed(self, context: AppContext, target_id: str) -> None:
        context.emit(
            "navigation.popup.dismissed",
            "弹窗处理完成",
            f"已处理弹窗: {target_id}",
            workflow_id="daily",
            status="success",
            data={"app_id": self.spec.identity.app_id, "target_id": target_id},
        )

    def _foreground_left_app(self, observation: Observation | None) -> bool:
        return bool(
            observation is not None
            and observation.activity.package_name
            and observation.activity.package_name != self.spec.identity.package_name
        )
