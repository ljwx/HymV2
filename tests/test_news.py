import unittest
from types import SimpleNamespace

from hym.apps.specs import NewsContentSpec
from hym.apps.targets import text_locator, target
from hym.core.models import ActivityInfo, AppIdentity, Observation, SystemKey, WorkflowStatus
from hym.core.pages import ObservationProfile, PageMatchResult, PageMatchStatus
from hym.runtime.news import NewsContentTask


class _Actions:
    def __init__(self) -> None:
        observation = Observation(
            "device-1",
            ActivityInfo("com.external.video", "VideoActivity"),
        )
        self.page_result = PageMatchResult(
            "qutoutiao.news.detail",
            PageMatchStatus.NOT_MATCHED,
            observation,
            message="前台包名不符",
        )
        self.matched_pages = []
        self.pressed = []
        self.swipes = 0

    def tap_target(self, target_spec, timeout=2.0):
        return True

    def match_page(self, page):
        self.matched_pages.append(page)
        return self.page_result

    def press(self, key):
        self.pressed.append(key)
        return True

    def swipe_up(self):
        self.swipes += 1
        return True


class _Navigation:
    def __init__(self) -> None:
        self.calls = 0

    def go_home(self, context, *, select_tab=False):
        self.calls += 1
        return True


class NewsContentTaskTest(unittest.TestCase):
    def test_external_app_is_not_counted_as_article_detail(self):
        actions = _Actions()
        navigation = _Navigation()
        events = []
        progress = {}
        context = SimpleNamespace(
            app=AppIdentity("qutoutiao", "com.jifen.qukan", "趣头条"),
            observation_profile=ObservationProfile(),
            actions=actions,
            timing=SimpleNamespace(wait=lambda seconds: None, operation_delay=lambda *args: None),
            sample_count=lambda *args: 1,
            option=lambda key, default: default,
            step_progress=lambda step_id: progress,
            clear_step_progress=lambda step_id: progress.clear(),
            emit=lambda event_type, event_name, message, **kwargs: events.append(
                (event_type, event_name, message, kwargs)
            ),
        )
        spec = NewsContentSpec(
            feed_item=target("随机文章", text_locator("标题", "文章")),
            detail_marker=target("文章详情", text_locator("评论", "我来说两句")),
        )

        outcome = NewsContentTask(spec, navigation).run(context)

        self.assertEqual(WorkflowStatus.NO_PROGRESS, outcome.status)
        self.assertEqual(2, navigation.calls)
        self.assertEqual([SystemKey.BACK], actions.pressed)
        self.assertEqual(1, actions.swipes)
        self.assertEqual("com.jifen.qukan", actions.matched_pages[0].package_name)
        self.assertEqual("content.external.skipped", events[0][0])
        self.assertEqual("com.external.video", events[0][3]["data"]["external_package"])


if __name__ == "__main__":
    unittest.main()
