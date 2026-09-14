import unittest
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from hym.apps.app_specs.qutoutiao import QutoutiaoTaskPageNavigator
from hym.apps.app_specs.ximalaya import XimalayaPlayback
from hym.apps.catalog import douyin_spec, kuaishou_spec, qutoutiao_spec, ximalaya_spec
from hym.core.models import ActivityInfo, Observation, Point, SystemKey, WorkflowStatus
from hym.core.pages import PageMatchResult, PageMatchStatus
from hym.core.targets import LocatorKind, ResolveResult, ResolveStatus, ResolvedTarget
from hym.runtime.interruption import InterruptionKind, InterruptionRequest, WorkflowYield
from hym.runtime.audio import DefaultAudioPlayback
from hym.runtime.navigation import NavigationController
from hym.runtime.video import VideoContentTask


def _found(target, observation):
    return ResolveResult(
        ResolveStatus.FOUND,
        ResolvedTarget(
            target.target_id,
            "测试定位",
            Point(0.5, 0.5),
            1.0,
            observation.observation_id,
        ),
    )


class StubActions:
    def __init__(self, pages, packages=None, activities=None, visual_match=None):
        self.pages = list(pages)
        self.packages = list(packages or [])
        self.activities = list(activities or [])
        self.visual_match = visual_match
        self.current = set()
        self.observation_count = 0
        self.tapped = []
        self.pressed = []
        self.swipe_count = 0

    def observe(self, *, include_ui_tree, include_screenshot):
        self.current = self.pages.pop(0)
        self.observation_count += 1
        package = self.packages.pop(0) if self.packages else "com.kuaishou.nebula"
        activity = self.activities.pop(0) if self.activities else "HomeActivity"
        return Observation(
            "device-1",
            ActivityInfo(package, activity),
            observation_id=f"observation-{self.observation_count}",
        )

    def observe_for(self, targets, *, include_screenshot):
        return self.observe(include_ui_tree=True, include_screenshot=include_screenshot)

    def match_page(self, page, *, observation=None, extra_targets=(), visual_fallback=True):
        observation = observation or self.observe(include_ui_tree=True, include_screenshot=False)
        forbidden = tuple(
            target.target_id for target in page.forbidden_markers if target.target_id in self.current
        )
        matched = tuple(target.target_id for target in page.markers if target.target_id in self.current)
        status = (
            PageMatchStatus.MATCHED
            if not forbidden
            and observation.activity.package_name == page.package_name
            and len(matched) >= page.minimum_markers
            else PageMatchStatus.NOT_MATCHED
        )
        message = ""
        if observation.activity.package_name != page.package_name:
            message = f"前台包名不符: {observation.activity.package_name}"
        elif page.activity_patterns and not any(
            re.search(pattern, observation.activity.activity_name or "")
            for pattern in page.activity_patterns
        ):
            message = f"Activity 不符: {observation.activity.activity_name}"
        return PageMatchResult(
            page.page_id,
            status,
            observation,
            matched_markers=matched,
            forbidden_markers=forbidden,
            message=message,
        )

    def resolve_in(self, target, observation):
        if target.target_id in self.current:
            return _found(target, observation)
        return ResolveResult(ResolveStatus.NOT_FOUND)

    def tap_resolved(self, target):
        self.tapped.append(target.target_id)
        return True

    def tap_target(self, target, timeout=2.0):
        observation = self.observe(include_ui_tree=True, include_screenshot=False)
        result = self.resolve_in(target, observation)
        if not result.found or result.target is None:
            return False
        return self.tap_resolved(result.target)

    def press(self, key):
        self.pressed.append(key)
        return True

    def swipe_up(self):
        self.swipe_count += 1
        return True

    def needs_screenshot(self, targets):
        return self.visual_match is not None and any(
            target.target_id == self.visual_match for target in targets
        )

    def resolve_many(self, *args, **kwargs):
        if self.visual_match is None:
            raise AssertionError("没有视觉目标时不应重复解析 UI")
        target = next(item for item in args[0] if item.target_id == self.visual_match)
        observation = Observation(
            "device-1",
            ActivityInfo("com.kuaishou.nebula", "HomeActivity"),
        )
        return target, _found(target, observation)


class StubTiming:
    def __init__(self):
        self.operation_delays = 0
        self.elapsed = 0.0
        self.started = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.clock = SimpleNamespace(sleep=self._sleep, now=self._now)

    def _sleep(self, seconds):
        self.elapsed += seconds

    def _now(self):
        return self.started + timedelta(seconds=self.elapsed)

    def operation_delay(self, *args):
        self.operation_delays += 1

    def baseline_seconds(self, seconds, *, reward_wait=False):
        return seconds

    def wait(self, seconds):
        pass

    def range_seconds(
        self,
        start,
        end,
        *,
        center=None,
        stddev=None,
        reward_wait=False,
    ):
        return start


class StubRandom:
    def randint(self, start, end):
        return start

    def random(self):
        return 1.0


def _context(actions):
    session = SimpleNamespace(starts=[])
    session.start_app = lambda app: session.starts.append(app.package_name)
    runtime_progress = {}
    events = []
    context = SimpleNamespace(
        actions=actions,
        session=session,
        timing=StubTiming(),
        random=StubRandom(),
        option=lambda key, default: 1 if key in {"content_count_min", "content_count_max"} else default,
        emit=lambda *args, **kwargs: events.append((args, kwargs)),
        events=events,
    )
    context.step_progress = lambda step_id: runtime_progress.setdefault(step_id, {})
    context.clear_step_progress = lambda step_id: runtime_progress.pop(step_id, None)
    context.reach_safe_point = lambda checkpoint, **data: None
    context.sample_count = lambda prefix, minimum, maximum, **kwargs: int(
        context.option(f"{prefix}_min", minimum)
    )
    context.sample_seconds = lambda prefix, minimum, maximum, **kwargs: context.timing.range_seconds(
        float(context.option(f"{prefix}_min", minimum)),
        float(context.option(f"{prefix}_max", maximum)),
    )
    return context


class NavigationEfficiencyTest(unittest.TestCase):
    def setUp(self):
        self.spec = kuaishou_spec()
        self.navigation = NavigationController(self.spec)
        self.video = VideoContentTask(self.spec.identity, self.spec.video, self.navigation)

    def test_home_and_tab_use_one_observation(self):
        actions = StubActions(
            [{self.spec.navigation.home_marker.target_id, self.spec.navigation.home_tab.target_id}]
        )

        self.assertTrue(self.navigation.go_home(_context(actions), select_tab=True))

        self.assertEqual(1, actions.observation_count)
        self.assertEqual([self.spec.navigation.home_tab.target_id], actions.tapped)
        self.assertEqual([], actions.pressed)

    def test_douyin_does_not_reselect_home_tab_on_video_feed(self):
        spec = douyin_spec()
        actions = StubActions(
            [
                {
                    *(target.target_id for target in spec.navigation.home_page.markers),
                    spec.navigation.home_tab.target_id,
                }
            ],
            packages=[spec.identity.package_name],
            activities=["SplashActivity"],
        )

        self.assertTrue(NavigationController(spec).go_home(_context(actions), select_tab=True))

        self.assertEqual(1, actions.observation_count)
        self.assertEqual([], actions.tapped)
        self.assertEqual([], actions.pressed)

    def test_douyin_still_selects_home_tab_when_video_feed_is_missing(self):
        spec = douyin_spec()
        actions = StubActions(
            [
                {spec.navigation.home_tab.target_id},
                {
                    *(target.target_id for target in spec.navigation.home_page.markers),
                    spec.navigation.home_tab.target_id,
                },
            ],
            packages=[spec.identity.package_name, spec.identity.package_name],
            activities=["SplashActivity", "SplashActivity"],
        )

        self.assertTrue(NavigationController(spec).go_home(_context(actions), select_tab=True))

        self.assertEqual(2, actions.observation_count)
        self.assertEqual([spec.navigation.home_tab.target_id], actions.tapped)
        self.assertEqual([], actions.pressed)

    def test_missing_home_tab_is_reobserved_before_recovery(self):
        actions = StubActions(
            [
                {self.spec.navigation.home_marker.target_id},
                {self.spec.navigation.home_marker.target_id, self.spec.navigation.home_tab.target_id},
            ]
        )

        self.assertTrue(self.navigation.go_home(_context(actions), select_tab=True))

        self.assertEqual(2, actions.observation_count)
        self.assertEqual([self.spec.navigation.home_tab.target_id], actions.tapped)
        self.assertEqual([], actions.pressed)

    def test_popup_is_checked_only_after_home_is_missing(self):
        close_target = self.spec.navigation.home_intercepts[0].close_target
        actions = StubActions(
            [
                {close_target.target_id},
                {self.spec.navigation.home_marker.target_id},
            ]
        )

        self.assertTrue(self.navigation.go_home(_context(actions)))

        self.assertEqual(2, actions.observation_count)
        self.assertEqual([close_target.target_id], actions.tapped)
        self.assertEqual([], actions.pressed)

    def test_task_page_uses_visible_home_tab_before_back(self):
        actions = StubActions(
            [
                {self.spec.navigation.task_marker.target_id, self.spec.navigation.home_tab.target_id},
                {self.spec.navigation.home_marker.target_id, self.spec.navigation.home_tab.target_id},
            ]
        )

        self.assertTrue(self.navigation.go_home(_context(actions)))

        self.assertEqual(2, actions.observation_count)
        self.assertEqual([self.spec.navigation.home_tab.target_id], actions.tapped)
        self.assertEqual([], actions.pressed)

    def test_home_relaunches_once_when_foreground_left_app(self):
        actions = StubActions(
            [set(), {self.spec.navigation.home_marker.target_id}],
            packages=["com.miui.home", "com.kuaishou.nebula"],
        )
        context = _context(actions)

        self.assertTrue(self.navigation.go_home(context))

        self.assertEqual(["com.kuaishou.nebula"], context.session.starts)
        self.assertEqual([SystemKey.HOME], actions.pressed)

    def test_known_startup_activity_waits_without_restarting(self):
        spec = ximalaya_spec()
        actions = StubActions(
            [set(), {target.target_id for target in spec.navigation.home_page.markers}],
            packages=[spec.identity.package_name, spec.identity.package_name],
            activities=[
                "com.ximalaya.ting.android.host.activity.WelComeActivity",
                "com.ximalaya.ting.android.host.activity.MainActivity",
            ],
        )
        context = _context(actions)

        self.assertTrue(NavigationController(spec).go_home(context))

        self.assertEqual([], actions.pressed)
        self.assertEqual([], context.session.starts)

    def test_audio_playback_accepts_already_playing_state(self):
        spec = ximalaya_spec()
        audio = spec.content
        actions = StubActions(
            [{audio.session_marker.target_id, audio.playing_target.target_id}],
            packages=[spec.identity.package_name],
        )
        context = _context(actions)

        self.assertTrue(DefaultAudioPlayback().ensure_playing(context, audio))

        self.assertEqual(1, actions.observation_count)
        self.assertEqual([], actions.tapped)

    def test_audio_playback_taps_resume_from_same_observation(self):
        spec = ximalaya_spec()
        audio = spec.content
        actions = StubActions(
            [{audio.session_marker.target_id, audio.resume_target.target_id}],
            packages=[spec.identity.package_name],
        )
        context = _context(actions)

        self.assertTrue(DefaultAudioPlayback().ensure_playing(context, audio))

        self.assertEqual(1, actions.observation_count)
        self.assertEqual([audio.resume_target.target_id], actions.tapped)
        self.assertEqual(1, context.timing.operation_delays)

    def test_ximalaya_retries_once_when_playbar_loads_after_home(self):
        spec = ximalaya_spec()
        audio = spec.content
        actions = StubActions(
            [set(), {audio.session_marker.target_id, audio.resume_target.target_id}],
            packages=[spec.identity.package_name, spec.identity.package_name],
        )
        context = _context(actions)

        self.assertTrue(
            XimalayaPlayback(DefaultAudioPlayback()).ensure_playing(context, audio)
        )

        self.assertEqual(2, actions.observation_count)
        self.assertEqual([audio.resume_target.target_id], actions.tapped)
        self.assertEqual(2, context.timing.operation_delays)

    def test_qutoutiao_retries_task_navigation_after_handling_ad(self):
        spec = qutoutiao_spec()
        navigation = NavigationController(spec)
        navigator = QutoutiaoTaskPageNavigator(spec, navigation)
        context = _context(StubActions([]))

        with patch.object(
            QutoutiaoTaskPageNavigator,
            "_recover_ad",
            side_effect=[False, True],
        ) as recover_ad, patch.object(
            NavigationController,
            "go_task_page",
            side_effect=[False, True],
        ) as go_task_page:
            self.assertTrue(navigator(context))

        self.assertEqual(2, recover_ad.call_count)
        self.assertEqual(2, go_task_page.call_count)

    def test_douyin_sign_in_ocr_accepts_observed_confidence(self):
        target_spec = douyin_spec().check_in.stages[2].action_targets[0]
        ocr = next(locator for locator in target_spec.locators if locator.kind is LocatorKind.OCR_TEXT)

        self.assertEqual("立即签到领", ocr.query)
        self.assertEqual(0.45, ocr.min_confidence)

    def test_douyin_duration_reward_accepts_observed_popup_title(self):
        target_spec = douyin_spec().duration_reward.success_target
        queries = {locator.query for locator in target_spec.locators}

        self.assertIn("开宝箱奖励已到账", queries)
        self.assertIn("获得开宝箱奖励", queries)

    def test_kuaishou_navigation_uses_instrumentation_tree(self):
        targets = (
            self.spec.navigation.home_marker,
            self.spec.navigation.home_tab,
            self.spec.navigation.task_entry,
            self.spec.navigation.task_marker,
        )

        self.assertTrue(
            all(target.metadata.get("ui_tree_source") == "instrumentation" for target in targets)
        )

    def test_kuaishou_reward_ad_can_be_recognized_by_activity(self):
        activity_target = self.spec.ad.start_markers[0]
        locator = activity_target.locators[0]

        self.assertEqual("快手激励广告页面", activity_target.target_id)
        self.assertEqual(LocatorKind.ACTIVITY, locator.kind)
        self.assertEqual("com.kuaishou.nebula", locator.options["package_name"])

    def test_check_in_keeps_current_and_legacy_locators_in_one_stage(self):
        action_target = self.spec.check_in.stages[0].action_targets[0]
        kinds = {locator.kind for locator in action_target.locators}

        self.assertEqual(
            {LocatorKind.UI_TEXT, LocatorKind.OCR_TEXT, LocatorKind.IMAGE},
            kinds,
        )
        self.assertTrue(
            all(
                locator.query == "立即签到"
                for locator in action_target.locators
                if locator.kind is not LocatorKind.IMAGE
            )
        )

    def test_unclassified_video_reuses_observation_without_interaction(self):
        actions = StubActions(
            [
                {self.spec.navigation.home_marker.target_id, self.spec.navigation.home_tab.target_id},
                {self.spec.video.feed_marker.target_id},
            ]
        )

        outcome = self.video.run(_context(actions))

        self.assertEqual(WorkflowStatus.SUCCESS, outcome.status)
        self.assertEqual(0, outcome.outputs["normal"])
        self.assertEqual(2, actions.observation_count)
        self.assertEqual(1, actions.swipe_count)

    def test_unclassified_video_can_be_treated_as_suspected_ad(self):
        actions = StubActions(
            [
                {self.spec.navigation.home_marker.target_id, self.spec.navigation.home_tab.target_id},
                {self.spec.video.feed_marker.target_id},
            ]
        )
        context = _context(actions)
        original_option = context.option
        context.option = lambda key, default: (
            True if key == "treat_unclassified_as_suspected_ad" else original_option(key, default)
        )

        with patch.object(VideoContentTask, "_run_interactions") as interactions:
            outcome = self.video.run(context)

        self.assertEqual(WorkflowStatus.SUCCESS, outcome.status)
        self.assertAlmostEqual(1.0, context.timing.elapsed)
        self.assertEqual(0, outcome.outputs["normal"])
        interactions.assert_not_called()
        suspected_event = next(
            item for item in context.events if item[0][0] == "content.ad.suspected"
        )
        self.assertEqual(
            "suspected_ad",
            suspected_event[1]["data"]["classification_kind"],
        )
        self.assertEqual(
            "关键分类标记未命中",
            suspected_event[1]["data"]["classification_reason"],
        )

    def test_classified_normal_video_can_run_interactions(self):
        normal_marker = self.spec.video.normal_markers[0]
        actions = StubActions(
            [
                {self.spec.navigation.home_marker.target_id, self.spec.navigation.home_tab.target_id},
                {self.spec.video.feed_marker.target_id, normal_marker.target_id},
            ]
        )
        context = _context(actions)

        with patch.object(VideoContentTask, "_run_interactions") as interactions:
            outcome = self.video.run(context)

        self.assertEqual(WorkflowStatus.SUCCESS, outcome.status)
        self.assertEqual(1, outcome.outputs["normal"])
        self.assertGreaterEqual(context.timing.elapsed, 10.0)
        interactions.assert_called_once()

    def test_normal_video_can_use_long_full_watch_attempt(self):
        normal_marker = self.spec.video.normal_markers[0]
        actions = StubActions(
            [
                {self.spec.navigation.home_marker.target_id, self.spec.navigation.home_tab.target_id},
                {self.spec.video.feed_marker.target_id, normal_marker.target_id},
            ]
        )
        context = _context(actions)
        context.random.random = lambda: 0.1

        with patch.object(VideoContentTask, "_run_interactions"):
            outcome = self.video.run(context)

        self.assertEqual(WorkflowStatus.SUCCESS, outcome.status)
        self.assertGreaterEqual(context.timing.elapsed, 25.0)

    def test_uninterested_video_skips_interactions(self):
        normal_marker = self.spec.video.normal_markers[0]
        actions = StubActions(
            [
                {self.spec.navigation.home_marker.target_id, self.spec.navigation.home_tab.target_id},
                {self.spec.video.feed_marker.target_id, normal_marker.target_id},
            ]
        )
        context = _context(actions)
        context.random.random = lambda: 0.0

        with patch.object(VideoContentTask, "_run_interactions") as interactions:
            outcome = self.video.run(context)

        self.assertEqual(WorkflowStatus.SUCCESS, outcome.status)
        self.assertGreaterEqual(context.timing.elapsed, 3.0)
        interactions.assert_not_called()

    def test_video_ad_only_waits_briefly_without_interactions(self):
        ad_marker = self.spec.video.ad_markers[0]
        actions = StubActions(
            [
                {self.spec.navigation.home_marker.target_id, self.spec.navigation.home_tab.target_id},
                {self.spec.video.feed_marker.target_id, ad_marker.target_id},
            ]
        )
        context = _context(actions)

        with patch.object(VideoContentTask, "_run_interactions") as interactions:
            outcome = self.video.run(context)

        self.assertEqual(WorkflowStatus.SUCCESS, outcome.status)
        self.assertEqual(0, outcome.outputs["normal"])
        self.assertAlmostEqual(0.5, context.timing.elapsed)
        interactions.assert_not_called()

    def test_visual_ad_overrides_normal_marker(self):
        normal_marker = self.spec.video.normal_markers[0]
        visual_ad = next(
            target for target in self.spec.video.ad_markers if target.target_id == "快手推广文案"
        )
        actions = StubActions(
            [
                {self.spec.navigation.home_marker.target_id, self.spec.navigation.home_tab.target_id},
                {self.spec.video.feed_marker.target_id, normal_marker.target_id},
            ],
            visual_match=visual_ad.target_id,
        )

        with patch.object(VideoContentTask, "_run_interactions") as interactions:
            outcome = self.video.run(_context(actions))

        self.assertEqual(WorkflowStatus.SUCCESS, outcome.status)
        self.assertEqual(0, outcome.outputs["normal"])
        interactions.assert_not_called()

    def test_video_resume_does_not_repeat_completed_item(self):
        normal_marker = self.spec.video.normal_markers[0]
        home = {
            self.spec.navigation.home_marker.target_id,
            self.spec.navigation.home_tab.target_id,
        }
        feed = {self.spec.video.feed_marker.target_id, normal_marker.target_id}
        actions = StubActions([home, feed, home, feed])
        context = _context(actions)
        context.option = lambda key, default: (
            2 if key in {"content_count_min", "content_count_max"} else default
        )
        paused = False

        def pause_once(checkpoint, **data):
            nonlocal paused
            if not paused:
                paused = True
                raise WorkflowYield(
                    InterruptionRequest(InterruptionKind.APP_SWITCH, checkpoint, data)
                )

        context.reach_safe_point = pause_once
        with patch.object(VideoContentTask, "_run_interactions") as interactions:
            with self.assertRaises(WorkflowYield):
                self.video.run(context)
            context.reach_safe_point = lambda checkpoint, **data: None
            outcome = self.video.run(context)

        self.assertEqual(WorkflowStatus.SUCCESS, outcome.status)
        self.assertEqual(2, outcome.outputs["requested"])
        self.assertEqual(2, outcome.outputs["viewed"])
        self.assertEqual(2, actions.swipe_count)
        self.assertEqual(2, interactions.call_count)


if __name__ == "__main__":
    unittest.main()
