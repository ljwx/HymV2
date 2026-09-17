from __future__ import annotations

from dataclasses import dataclass

from hym.apps.specs import NewsContentSpec
from hym.core.models import SystemKey, WorkflowStatus
from hym.core.pages import PageSpec
from hym.runtime.context import AppContext
from hym.runtime.navigation import NavigationController
from hym.runtime.workflow import StepOutcome


@dataclass(frozen=True, slots=True)
class NewsContentTask:
    """浏览文章内容；页面目标和概率均由对应 App 提供。"""

    spec: NewsContentSpec
    navigation: NavigationController

    def run(self, context: AppContext) -> StepOutcome:
        if not self.navigation.go_home(context, select_tab=True):
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
        detail_page = PageSpec(
            f"{context.app.app_id}.news.detail",
            context.app.package_name,
            (self.spec.detail_marker,),
            observation_profile=context.observation_profile,
        )
        for index in range(int(progress.get("next_index", 1)), count + 1):
            if not context.actions.tap_target(self.spec.feed_item, timeout=2.0):
                context.actions.swipe_up()
                context.timing.operation_delay()
                continue
            context.timing.wait(float(context.option("detail_wait_seconds", 3.0)))
            detail_result = context.actions.match_page(detail_page)
            if not detail_result.matched:
                activity = detail_result.observation.activity if detail_result.observation else None
                external_package = activity.package_name if activity else ""
                if external_package and external_package != context.app.package_name:
                    context.emit(
                        "content.external.skipped",
                        "外部推广已跳过",
                        f"第 {index} 个信息流卡片打开了外部应用，返回新闻首页",
                        workflow_id="daily",
                        step_id="浏览内容",
                        status="skipped",
                        data={"index": index, "external_package": external_package},
                    )
                context.actions.press(SystemKey.BACK)
                if external_package and external_package != context.app.package_name:
                    context.timing.operation_delay()
                    self.navigation.go_home(context)
                context.actions.swipe_up()
                continue

            read_to_bottom = context.random.random() < float(
                context.option("read_to_bottom_probability", 0.75)
            )
            scroll_prefix = "news_bottom_swipes" if read_to_bottom else "news_partial_swipes"
            scroll_min, scroll_max = ((4, 8) if read_to_bottom else (1, 3))
            for _ in range(context.sample_count(scroll_prefix, scroll_min, scroll_max)):
                context.actions.swipe_up()
                context.timing.clock.sleep(
                    context.sample_seconds("news_scroll_pause_seconds", 1.5, 4.0)
                )
                if read_to_bottom and self.spec.bottom_marker is not None:
                    if context.actions.exists(self.spec.bottom_marker, timeout=0.4):
                        break
            if self.spec.like_target is not None and context.random.random() < float(
                context.option("like_probability", 0.17)
            ):
                context.actions.tap_target(self.spec.like_target, timeout=0.8)
            if self.spec.comment_target is not None and context.random.random() < float(
                context.option("comment_probability", 0.15)
            ):
                if context.actions.tap_target(self.spec.comment_target, timeout=0.8):
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
