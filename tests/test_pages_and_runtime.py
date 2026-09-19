import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from hym.apps.catalog import douyin_spec, kuaishou_spec, qutoutiao_spec, ximalaya_spec
from hym.apps.plugin import create_daily_plugin
from hym.core.config import AppRunSettings, BehaviorSettings
from hym.core.events import InMemoryEventSink
from hym.core.models import (
    ActionStatus,
    ActivityInfo,
    AppIdentity,
    DeviceDescriptor,
    ImageFrame,
    Observation,
    ObservationResult,
    Point,
    Rect,
    UiNode,
    UiTreeSource,
)
from hym.core.pages import ObservationProfile, PageMatchStatus, PageSpec
from hym.core.targets import LocatorKind, LocatorSpec, ResolveResult, ResolveStatus, ResolvedTarget, TargetSpec
from hym.locators.hybrid import HybridLocator
from hym.runtime.actions import ActionController
from hym.runtime.behavior import BehaviorTiming
from hym.runtime.context import AppContext, DailyActionStatus
from hym.runtime.lease import DeviceBusyError, DeviceLease
from hym.runtime.rewards import CheckInTask
from hym.runtime.workflow import StepOutcome
from hym.testing import DeterministicRandom, FakeClock, InMemoryStateStore


class StubDiagnostics:
    def capture(self, *args, **kwargs):
        return ()


class StubOcr:
    def recognize(self, frame, region=None):
        from hym.core.models import OcrText

        return (OcrText("目标页", Rect(0.2, 0.2, 0.4, 0.3), 0.99, "测试OCR"),)


class StubSession:
    descriptor = DeviceDescriptor("device-1")

    def __init__(self, package="com.example", activity="MainActivity", nodes=()):
        self.package = package
        self.activity = activity
        self.nodes = tuple(nodes)
        self.requests = []

    def observe(self, request):
        self.requests.append(request)
        frame = ImageFrame(1, 1, b"\x00\x00\x00") if request.include_screenshot else None
        return ObservationResult(
            ActionStatus.SUCCESS,
            Observation(
                "device-1",
                ActivityInfo(self.package, self.activity),
                ui_nodes=self.nodes,
                screenshot=frame,
            ),
        )


def create_actions(session, *, ocr=None, profile=None, clock=None):
    clock = clock or FakeClock()
    random_source = DeterministicRandom()
    context = AppContext(
        app=AppIdentity("app", "com.example", "示例"),
        settings=AppRunSettings("app"),
        session=session,
        timing=BehaviorTiming(BehaviorSettings(), clock, random_source),
        random_source=random_source,
        state=InMemoryStateStore(),
        events=InMemoryEventSink(),
        diagnostics=StubDiagnostics(),
        observation_profile=profile,
    )
    return context, ActionController(context, HybridLocator(random_source, ocr_engine=ocr))


def text_target(target_id, text):
    return TargetSpec(target_id, (LocatorSpec("文字", LocatorKind.UI_TEXT, text),))


class PageMatcherTest(unittest.TestCase):
    def test_page_signal_cannot_be_only_a_coordinate(self):
        marker = TargetSpec(
            "固定坐标",
            (LocatorSpec("坐标", LocatorKind.COORDINATE, options={"point": (0.5, 0.5)}),),
        )

        with self.assertRaisesRegex(ValueError, "不能只使用固定坐标"):
            PageSpec("example.invalid", "com.example", (marker,))

    def test_page_requires_package_activity_and_all_required_signals(self):
        nodes = (
            UiNode("1", None, text="首页", bounds=Rect(0.0, 0.9, 0.2, 1.0)),
            UiNode("2", None, resource_id="com.example:id/feed", bounds=Rect(0.0, 0.1, 1.0, 0.9)),
        )
        session = StubSession(nodes=nodes)
        _, actions = create_actions(session)
        page = PageSpec(
            "example.home",
            "com.example",
            (
                text_target("首页", "首页"),
                TargetSpec("信息流", (LocatorSpec("ID", LocatorKind.UI_ID, "com.example:id/feed"),)),
            ),
            activity_patterns=(r"MainActivity$",),
            minimum_markers=2,
        )

        self.assertTrue(actions.match_page(page).matched)

        session.package = "com.other"
        result = actions.match_page(page)
        self.assertEqual(PageMatchStatus.NOT_MATCHED, result.status)
        self.assertIn("前台包名不符", result.message)

    def test_forbidden_signal_rejects_visually_similar_page(self):
        nodes = (
            UiNode("1", None, text="首页", bounds=Rect(0.0, 0.9, 0.2, 1.0)),
            UiNode("2", None, text="任务中心", bounds=Rect(0.2, 0.2, 0.8, 0.3)),
        )
        _, actions = create_actions(StubSession(nodes=nodes))
        page = PageSpec(
            "example.home",
            "com.example",
            (text_target("首页", "首页"),),
            forbidden_markers=(text_target("任务页", "任务中心"),),
        )

        result = actions.match_page(page)

        self.assertFalse(result.matched)
        self.assertEqual(("任务页",), result.forbidden_markers)

    def test_visual_page_signal_runs_only_as_fallback(self):
        session = StubSession()
        profile = ObservationProfile(UiTreeSource.APPLICATION, screenshot_max_size=720)
        _, actions = create_actions(session, ocr=StubOcr(), profile=profile)
        marker = TargetSpec(
            "OCR页面",
            (LocatorSpec("OCR", LocatorKind.OCR_TEXT, "目标页", options={"mode": "exact"}),),
        )

        result = actions.match_page(PageSpec("example.ocr", "com.example", (marker,)))

        self.assertTrue(result.matched)
        self.assertEqual([False, True], [item.include_screenshot for item in session.requests])
        self.assertTrue(all(item.ui_tree_source is UiTreeSource.APPLICATION for item in session.requests))
        self.assertEqual(720, session.requests[-1].screenshot_max_size)


class RuntimeStateTest(unittest.TestCase):
    def test_daily_key_is_frozen_when_context_crosses_midnight(self):
        clock = FakeClock(datetime(2026, 9, 13, 23, 59, tzinfo=timezone.utc))
        context, _ = create_actions(StubSession(), clock=clock)
        original_key = context.daily_key("balance")

        clock.sleep(48 * 60 * 60)

        self.assertEqual(original_key, context.daily_key("balance"))

    def test_daily_action_checkpoint_is_persisted(self):
        context, _ = create_actions(StubSession())

        self.assertEqual(DailyActionStatus.NOT_STARTED, context.daily_action_status("check_in"))
        context.mark_daily_action("check_in", DailyActionStatus.PENDING_CONFIRMATION)
        self.assertEqual(
            DailyActionStatus.PENDING_CONFIRMATION,
            context.daily_action_status("check_in"),
        )

    def test_device_lease_rejects_second_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "device.lock"
            first = DeviceLease(path)
            second = DeviceLease(path)
            first.acquire()
            try:
                with self.assertRaises(DeviceBusyError):
                    second.acquire()
            finally:
                first.release()

            second.acquire()
            second.release()

    def test_uncertain_check_in_is_not_clicked_twice(self):
        context, _ = create_actions(StubSession())
        spec = kuaishou_spec()
        task = CheckInTask(spec, lambda _: True)
        action_id = spec.check_in.stages[0].action_targets[0].target_id

        class CheckInActions:
            def __init__(self):
                self.taps = 0
                self.current = {action_id}

            def observe_for(self, targets, *, include_screenshot):
                return Observation("device-1", ActivityInfo("com.example", "MainActivity"))

            def resolve_in(self, target, observation):
                if target.target_id not in self.current:
                    return ResolveResult(ResolveStatus.NOT_FOUND)
                return ResolveResult(
                    ResolveStatus.FOUND,
                    ResolvedTarget(target.target_id, "测试", Point(0.5, 0.5), 1.0, "observation"),
                )

            def needs_screenshot(self, targets):
                return False

            def resolve_many(self, targets, *, include_screenshot):
                return None

            def tap_resolved(self, target):
                self.taps += 1
                self.current.clear()
                return True

        context.actions = CheckInActions()
        first = task.run(context)
        second = task.run(context)

        self.assertEqual("retryable_failure", first.status.value)
        self.assertEqual("retryable_failure", second.status.value)
        self.assertEqual(1, context.actions.taps)
        self.assertEqual(DailyActionStatus.UNCERTAIN, context.daily_action_status("check_in"))

    def test_check_in_dynamically_advances_multiple_stages(self):
        context, _ = create_actions(StubSession())
        spec = douyin_spec()
        task = CheckInTask(spec, lambda _: True)
        open_stage, _, confirm_stage = spec.check_in.stages
        success = spec.check_in.success_targets[0]

        class MultiStageActions:
            def __init__(self):
                self.states = [
                    {open_stage.action_targets[0].target_id},
                    {confirm_stage.action_targets[0].target_id},
                    {success.target_id},
                ]
                self.index = 0
                self.tapped = []
                self.pressed = []

            def observe_for(self, targets, *, include_screenshot):
                return Observation("device-1", ActivityInfo("com.example", "MainActivity"))

            def resolve_in(self, target, observation):
                if target.target_id not in self.states[self.index]:
                    return ResolveResult(ResolveStatus.NOT_FOUND)
                return ResolveResult(
                    ResolveStatus.FOUND,
                    ResolvedTarget(target.target_id, "测试", Point(0.5, 0.5), 1.0, "observation"),
                )

            def needs_screenshot(self, targets):
                return False

            def tap_resolved(self, target):
                self.tapped.append(target.target_id)
                self.index += 1
                return True

            def press(self, key):
                self.pressed.append(key)
                return True

        context.actions = MultiStageActions()
        outcome = task.run(context)

        self.assertEqual("success", outcome.status.value)
        self.assertEqual(
            [open_stage.action_targets[0].target_id, confirm_stage.action_targets[0].target_id],
            context.actions.tapped,
        )
        self.assertEqual(DailyActionStatus.CONFIRMED, context.daily_action_status("check_in"))

    def test_check_in_action_takes_priority_over_passive_success(self):
        context, _ = create_actions(StubSession())
        spec = qutoutiao_spec()
        task = CheckInTask(spec, lambda _: True)
        action = spec.check_in.stages[0].action_targets[0]
        passive = spec.check_in.passive_success_targets[0]

        class PassiveSuccessActions:
            def __init__(self):
                self.states = [{action.target_id, passive.target_id}, {passive.target_id}]
                self.index = 0
                self.tapped = []

            def observe_for(self, targets, *, include_screenshot):
                return Observation("device-1", ActivityInfo("com.example", "MainActivity"))

            def resolve_in(self, target, observation):
                if target.target_id not in self.states[self.index]:
                    return ResolveResult(ResolveStatus.NOT_FOUND)
                return ResolveResult(
                    ResolveStatus.FOUND,
                    ResolvedTarget(target.target_id, "测试", Point(0.5, 0.5), 1.0, "observation"),
                )

            def needs_screenshot(self, targets):
                return False

            def resolve_many(self, targets, *, include_screenshot):
                return None

            def tap_resolved(self, target):
                self.tapped.append(target.target_id)
                self.index += 1
                return True

        context.actions = PassiveSuccessActions()
        outcome = task.run(context)

        self.assertEqual("success", outcome.status.value)
        self.assertEqual([action.target_id], context.actions.tapped)


class ExtensibilityTest(unittest.TestCase):
    def test_content_handler_can_be_replaced_without_changing_workflow(self):
        called = []

        def handler(context):
            called.append("audio")
            return StepOutcome.success("自定义策略完成")

        plugin = create_daily_plugin(ximalaya_spec(), content_handler=handler)
        context = SimpleNamespace(option=lambda key, default: default)
        definition = plugin.build_workflow(context)
        content_step = next(step for step in definition.steps if step.step_id == "浏览内容")

        outcome = content_step.handler(context)

        self.assertEqual("success", outcome.status.value)
        self.assertEqual(["audio"], called)

    def test_real_observations_are_reflected_in_app_specs(self):
        douyin = douyin_spec()
        qutoutiao = qutoutiao_spec()
        ximalaya = ximalaya_spec()

        self.assertEqual(2, douyin.navigation.home_page.minimum_markers)
        self.assertEqual(
            (douyin.navigation.home_tab, douyin.content.feed_marker),
            douyin.navigation.home_page.markers,
        )
        self.assertTrue(
            any(
                locator.query == "推荐"
                for locator in douyin.content.feed_marker.locators
            )
        )
        self.assertIn(
            douyin.navigation.task_marker,
            douyin.navigation.home_page.forbidden_markers,
        )
        task_ocr = next(
            locator
            for locator in qutoutiao.navigation.task_entry.locators
            if locator.kind is LocatorKind.OCR_TEXT
        )
        self.assertEqual("exact", task_ocr.options["mode"])
        self.assertEqual("audio", ximalaya.content_kind)
        self.assertEqual("com.ximalaya.ting.lite", ximalaya.identity.package_name)

        ad_activity = qutoutiao.ad.start_markers[0]
        self.assertEqual("趣头条激励广告页面", ad_activity.target_id)
        self.assertEqual(
            {r"InciteADActivity$", r"MobRewardVideoActivity$"},
            {locator.query for locator in ad_activity.locators},
        )
        self.assertTrue(all(locator.kind is LocatorKind.ACTIVITY for locator in ad_activity.locators))
        self.assertTrue(qutoutiao.ad.exit_after_wait_with_back)
        self.assertIsNone(qutoutiao.ad_entry)
        self.assertEqual(8, qutoutiao.navigation.home_attempts)


if __name__ == "__main__":
    unittest.main()
