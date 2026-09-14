import unittest

from hym.core.config import AppRunSettings, BehaviorSettings
from hym.core.events import InMemoryEventSink
from hym.core.models import (
    ActionResult,
    ActionStatus,
    ActivityInfo,
    AppIdentity,
    DeviceDescriptor,
    ImageFrame,
    Observation,
    ObservationResult,
    OcrText,
    Point,
    Rect,
    UiTreeSource,
)
from hym.core.targets import LocatorKind, LocatorSpec, TargetSpec
from hym.locators.hybrid import HybridLocator
from hym.runtime.actions import ActionController
from hym.runtime.behavior import BehaviorTiming
from hym.runtime.context import AppContext
from hym.testing import DeterministicRandom, FakeClock, InMemoryStateStore


class StubSession:
    descriptor = DeviceDescriptor("device-1")

    def __init__(self):
        self.requests = []

    def observe(self, request):
        self.requests.append(request)
        return ObservationResult(
            ActionStatus.SUCCESS,
            Observation("device-1", ActivityInfo("com.example", "Main")),
        )

    def input_text(self, value):
        self.input_value = value
        return ActionResult.success("input_text")


class StubDiagnostics:
    def capture(self, *args, **kwargs):
        return ()


class StubOcrEngine:
    def recognize(self, frame, region=None):
        return (OcrText("签到", Rect(0.4, 0.4, 0.6, 0.6), 0.99, "测试OCR"),)


class ActionControllerTest(unittest.TestCase):
    def test_activity_only_target_does_not_request_ui_tree(self):
        clock = FakeClock()
        random_source = DeterministicRandom()
        session = StubSession()
        context = AppContext(
            app=AppIdentity("app", "com.example", "示例"),
            settings=AppRunSettings("app"),
            session=session,
            timing=BehaviorTiming(BehaviorSettings(), clock, random_source),
            random_source=random_source,
            state=InMemoryStateStore(),
            events=InMemoryEventSink(),
            diagnostics=StubDiagnostics(),
        )
        actions = ActionController(context, HybridLocator(random_source))
        target = TargetSpec(
            "页面",
            (
                LocatorSpec(
                    "Activity",
                    LocatorKind.ACTIVITY,
                    "Main",
                    options={"mode": "exact"},
                ),
            ),
        )

        actions.resolve(target, timeout=0)

        self.assertFalse(session.requests[0].include_ui_tree)
        self.assertFalse(session.requests[0].include_screenshot)

    def test_text_input_log_contains_only_length(self):
        clock = FakeClock()
        random_source = DeterministicRandom()
        session = StubSession()
        events = InMemoryEventSink()
        context = AppContext(
            app=AppIdentity("app", "com.example", "示例"),
            settings=AppRunSettings("app"),
            session=session,
            timing=BehaviorTiming(BehaviorSettings(), clock, random_source),
            random_source=random_source,
            state=InMemoryStateStore(),
            events=events,
            diagnostics=StubDiagnostics(),
        )
        actions = ActionController(context, HybridLocator(random_source))

        self.assertTrue(actions.input_text("不写入日志的正文"))

        event = events.events[-1]
        self.assertEqual({"text_length": 8}, event.data)
        self.assertNotIn("不写入日志的正文", event.message)

    def test_target_can_select_accessibility_tree(self):
        clock = FakeClock()
        random_source = DeterministicRandom()
        session = StubSession()
        context = AppContext(
            app=AppIdentity("app", "com.example", "示例"),
            settings=AppRunSettings("app"),
            session=session,
            timing=BehaviorTiming(BehaviorSettings(), clock, random_source),
            random_source=random_source,
            state=InMemoryStateStore(),
            events=InMemoryEventSink(),
            diagnostics=StubDiagnostics(),
        )
        actions = ActionController(context, HybridLocator(random_source))
        target = TargetSpec(
            "任务页",
            (LocatorSpec("文本", LocatorKind.UI_TEXT, "任务中心"),),
            metadata={"ui_tree_source": "accessibility"},
        )

        actions.resolve(target, timeout=0)

        self.assertEqual(UiTreeSource.ACCESSIBILITY, session.requests[0].ui_tree_source)

    def test_disabled_ocr_does_not_trigger_screenshot(self):
        clock = FakeClock()
        random_source = DeterministicRandom()
        session = StubSession()
        context = AppContext(
            app=AppIdentity("app", "com.example", "示例"),
            settings=AppRunSettings("app"),
            session=session,
            timing=BehaviorTiming(BehaviorSettings(), clock, random_source),
            random_source=random_source,
            state=InMemoryStateStore(),
            events=InMemoryEventSink(),
            diagnostics=StubDiagnostics(),
        )
        locator = HybridLocator(random_source)
        actions = ActionController(context, locator)
        target = TargetSpec(
            "签到",
            (
                LocatorSpec("文本", LocatorKind.UI_TEXT, "签到"),
                LocatorSpec("OCR", LocatorKind.OCR_TEXT, "签到"),
            ),
        )

        result = actions.resolve(target, timeout=0)

        self.assertFalse(result.found)
        self.assertFalse(actions.needs_screenshot((target,)))
        self.assertEqual(1, len(session.requests))
        self.assertFalse(session.requests[0].include_screenshot)

    def test_ocr_runs_before_coordinate_fallback(self):
        clock = FakeClock()
        random_source = DeterministicRandom()
        session = StubSession()
        original_observe = session.observe

        def observe(request):
            result = original_observe(request)
            if request.include_screenshot:
                return ObservationResult(
                    ActionStatus.SUCCESS,
                    Observation(
                        "device-1",
                        ActivityInfo("com.example", "Main"),
                        screenshot=ImageFrame(1, 1, b"\x00\x00\x00", "BGR"),
                    ),
                )
            return result

        session.observe = observe
        context = AppContext(
            app=AppIdentity("app", "com.example", "示例"),
            settings=AppRunSettings("app"),
            session=session,
            timing=BehaviorTiming(BehaviorSettings(), clock, random_source),
            random_source=random_source,
            state=InMemoryStateStore(),
            events=InMemoryEventSink(),
            diagnostics=StubDiagnostics(),
        )
        actions = ActionController(context, HybridLocator(random_source, ocr_engine=StubOcrEngine()))
        target_spec = TargetSpec(
            "签到",
            (
                LocatorSpec("文本", LocatorKind.UI_TEXT, "签到", priority=20),
                LocatorSpec("OCR", LocatorKind.OCR_TEXT, "签到", priority=80),
                LocatorSpec(
                    "坐标",
                    LocatorKind.COORDINATE,
                    priority=200,
                    options={"point": (0.8, 0.8)},
                ),
            ),
        )

        result = actions.resolve(target_spec, timeout=0)

        self.assertTrue(result.found)
        self.assertEqual("OCR", result.target.strategy_id)
        self.assertEqual([False, True], [request.include_screenshot for request in session.requests])


if __name__ == "__main__":
    unittest.main()
