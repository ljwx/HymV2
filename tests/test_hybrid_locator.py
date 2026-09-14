import unittest

from hym.core.models import ActivityInfo, Observation, OcrText, Point, Rect, UiNode
from hym.core.targets import LocatorKind, LocatorSpec, TargetSpec
from hym.locators.hybrid import HybridLocator
from hym.testing import DeterministicRandom


class HybridLocatorTest(unittest.TestCase):
    def setUp(self):
        self.locator = HybridLocator(DeterministicRandom())
        self.observation = Observation(
            "device-1",
            ActivityInfo("com.example", "Main"),
            ui_nodes=(
                UiNode("0", None, class_name="root", bounds=Rect(0, 0, 1, 1)),
                UiNode(
                    "0/0",
                    "0",
                    class_name="android.widget.TextView",
                    resource_id="com.example:id/task",
                    text="任务中心",
                    bounds=Rect(0.2, 0.2, 0.8, 0.3),
                    visible=True,
                    enabled=True,
                ),
            ),
        )

    def test_last_successful_strategy_is_tried_first_next_time(self):
        target = TargetSpec(
            "task",
            (
                LocatorSpec("missing-id", LocatorKind.UI_ID, "missing", priority=10),
                LocatorSpec("text", LocatorKind.UI_TEXT, "任务中心", priority=20),
            ),
        )

        first = self.locator.resolve(target, self.observation)
        second = self.locator.resolve(target, self.observation)

        self.assertEqual(2, len(first.attempts))
        self.assertEqual("text", second.attempts[0].strategy_id)
        self.assertEqual(1, len(second.attempts))

    def test_precomputed_ocr_text_can_resolve_target(self):
        observation = Observation(
            "device-1",
            ActivityInfo(),
            ocr_texts=(OcrText("立即签到", Rect(0.3, 0.4, 0.7, 0.5), 0.93, "fake"),),
        )
        target = TargetSpec(
            "check-in",
            (LocatorSpec("ocr", LocatorKind.OCR_TEXT, "签到", min_confidence=0.8),),
        )

        result = self.locator.resolve(target, observation)

        self.assertTrue(result.found)
        self.assertEqual(Point(0.5, 0.45), result.target.point)

    def test_disabled_ocr_reports_capability(self):
        self.assertFalse(self.locator.supports(LocatorKind.OCR_TEXT))
        self.assertFalse(self.locator.supports(LocatorKind.IMAGE))

    def test_activity_locator_supports_package_and_regex(self):
        observation = Observation(
            "device-1",
            ActivityInfo("com.tencent.mm", "com.tencent.mm.plugin.sns.ui.SnsTimeLineUI"),
        )
        target = TargetSpec(
            "朋友圈页面",
            (
                LocatorSpec(
                    "activity",
                    LocatorKind.ACTIVITY,
                    r"SnsTimeLineUI$",
                    options={"mode": "regex", "package_name": "com.tencent.mm"},
                ),
            ),
        )

        result = self.locator.resolve(target, observation)

        self.assertTrue(result.found)
        self.assertEqual("com.tencent.mm.plugin.sns.ui.SnsTimeLineUI", result.target.evidence)

    def test_query_can_select_direct_child_of_resource(self):
        observation = Observation(
            "device-1",
            ActivityInfo(),
            ui_nodes=(
                UiNode(
                    "0",
                    None,
                    resource_id="com.example:id/list",
                    bounds=Rect(0, 0.1, 1, 0.9),
                ),
                UiNode(
                    "0/0",
                    "0",
                    class_name="android.view.ViewGroup",
                    bounds=Rect(0, 0.1, 1, 0.3),
                    clickable=True,
                ),
            ),
        )
        target = TargetSpec(
            "随机列表项",
            (
                LocatorSpec(
                    "直接子项",
                    LocatorKind.UI_QUERY,
                    options={
                        "parent_resource_id": "com.example:id/list",
                        "clickable": True,
                        "pick": "random",
                    },
                ),
            ),
        )

        result = self.locator.resolve(target, observation)

        self.assertTrue(result.found)
        self.assertEqual("0/0", result.target.metadata["node_id"])


if __name__ == "__main__":
    unittest.main()
