"""App 规格声明使用的少量公共常量和目标构造器。"""

from __future__ import annotations

from dataclasses import dataclass

from hym.apps.specs import PopupDismissSpec
from hym.apps.targets import ocr_locator, target, text_locator
from hym.core.models import UiTreeSource
from hym.core.pages import PageSpec
from hym.core.targets import TargetSpec
from hym.runtime.context import AppContext
from hym.runtime.navigation import NavigationController

TEXT = "android.widget.TextView"
BUTTON = "android.widget.Button"
IMAGE = "android.widget.ImageView"
GROUP = "android.view.ViewGroup"
FRAME = "android.widget.FrameLayout"
RECYCLER = "androidx.recyclerview.widget.RecyclerView"


def text_target(
    target_id: str,
    text: str,
    *,
    contains: bool = False,
    required: bool = False,
    ui_tree_source: UiTreeSource | None = None,
) -> TargetSpec:
    """优先匹配文字节点，结构树不可用时再用 OCR 补充。"""

    return target(
        target_id,
        text_locator(f"{target_id}-Poco", text, contains=contains),
        ocr_locator(
            f"{target_id}-OCR",
            text,
            mode="contains" if contains else "exact",
        ),
        required=required,
        metadata={"ui_tree_source": ui_tree_source} if ui_tree_source else None,
    )


@dataclass(frozen=True, slots=True)
class TaskPagePopupNavigator:
    """任务页被指定弹窗遮挡时，有限关闭后再确认页面。"""

    navigation: NavigationController
    popups: tuple[PopupDismissSpec, ...]
    max_dismissals: int = 3
    check_after_entry: bool = False

    def __call__(self, context: AppContext) -> bool:
        reached = self.navigation.go_task_page(context)
        if reached and not self.check_after_entry:
            return True

        spec = self.navigation.spec
        task_page = spec.navigation.task_page or PageSpec(
            f"{spec.identity.app_id}.task",
            spec.identity.package_name,
            (spec.navigation.task_marker,),
        )
        targets = tuple(
            item
            for popup in self.popups
            for item in (popup.marker, popup.close_target)
            if item is not None
        )
        for _ in range(self.max_dismissals):
            observation = context.actions.observe_for(
                targets,
                include_screenshot=context.actions.needs_screenshot(targets),
            )
            if observation is None:
                break
            target_id = self.navigation.dismiss_popup_in(
                context,
                self.popups,
                observation,
            )
            if target_id is None:
                break
            self.navigation.emit_popup_dismissed(context, target_id)
            context.timing.operation_delay()
            if context.actions.match_page(task_page).matched:
                return True
        if reached:
            return True
        return self.navigation.go_task_page(context)
