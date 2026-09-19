import unittest

from hym.adapters.airtest_poco import AirtestPocoDeviceAdapter
from hym.core.models import (
    ActionStatus,
    AppIdentity,
    DeviceDescriptor,
    ObservationRequest,
    Point,
    SwipeGesture,
    SystemKey,
    UiTreeSource,
)


class StubImage:
    shape = (20, 10, 3)

    def tobytes(self):
        return b"\x00" * 600


class StubDev:
    def __init__(self):
        self.calls = []
        self.activity_output = (
            "topResumedActivity=ActivityRecord{123456 u0 "
            "com.example/com.example.RealActivity t123}"
        )

    def touch(self, position, duration):
        self.calls.append(("touch", position, duration))

    def swipe(self, start, end, duration):
        self.calls.append(("swipe", start, end, duration))

    def keyevent(self, key):
        self.calls.append(("keyevent", key))

    def text(self, value, enter=False):
        self.calls.append(("text", value, enter))

    def snapshot(self, max_size=None):
        self.calls.append(("snapshot", max_size))
        return StubImage()

    def shell(self, command):
        self.calls.append(("shell", command))
        if command.startswith("uiautomator dump"):
            return """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0"><node text="任务中心" resource-id="com.example:id/task"
class="android.widget.TextView" content-desc="" clickable="false" enabled="true"
selected="false" bounds="[100,200][900,400]" /></hierarchy>"""
        return self.activity_output

    def disconnect(self):
        self.calls.append(("disconnect",))


class StubPoco:
    def dump(self):
        return {
            "name": "root",
            "payload": {"type": "Root", "pos": [0.5, 0.5], "size": [1, 1], "visible": True},
            "children": [
                {
                    "name": "com.example:id/task",
                    "payload": {
                        "name": "com.example:id/task",
                        "resourceId": b"com.example:id/task",
                        "type": "android.widget.TextView",
                        "text": "任务中心",
                        "pos": [0.5, 0.8],
                        "size": [0.4, 0.1],
                        "clickable": False,
                        "touchable": True,
                        "visible": True,
                    },
                }
            ],
        }


class BrokenPoco:
    def dump(self):
        raise RuntimeError("测试树失败")


class StubManager:
    device_ready = True

    def __init__(self):
        self.dev = StubDev()
        self.poco = StubPoco()
        self.started = []
        self.stopped = []
        self.top_activity = ("com.example", "MainActivity")

    def get_screen_size(self):
        return 1000, 2000

    def get_top_activity(self):
        return self.top_activity

    def start_app(self, package_name):
        self.started.append(package_name)

    def stop_app(self, package_name):
        self.stopped.append(package_name)


class AirtestPocoDeviceAdapterTest(unittest.TestCase):
    def setUp(self):
        self.manager = StubManager()
        self.adapter = AirtestPocoDeviceAdapter(
            DeviceDescriptor("device-1", connection="serial-1"),
            manager=self.manager,
        )
        self.app = AppIdentity("app-1", "com.example", "示例")

    def test_translates_normalized_touch_and_swipe_to_pixels(self):
        self.adapter.tap(Point(0.25, 0.5), duration_seconds=0.2)
        self.adapter.swipe(SwipeGesture(Point(0.5, 0.8), Point(0.5, 0.2), 0.3))

        self.assertEqual(("touch", (250, 1000), 0.2), self.manager.dev.calls[0])
        self.assertEqual(("swipe", (500, 1600), (500, 400), 0.3), self.manager.dev.calls[1])

    def test_passes_package_name_when_stopping_app(self):
        result = self.adapter.stop_app(self.app)

        self.assertTrue(result.succeeded)
        self.assertEqual(["com.example"], self.manager.stopped)

    def test_observation_contains_neutral_ui_nodes_and_frame(self):
        result = self.adapter.observe(ObservationRequest(include_ui_tree=True, include_screenshot=True))

        self.assertTrue(result.succeeded)
        observation = result.observation
        self.assertEqual("com.example", observation.activity.package_name)
        self.assertEqual("com.example.RealActivity", observation.activity.activity_name)
        self.assertEqual("com.example:id/task", observation.ui_nodes[1].resource_id)
        self.assertEqual("任务中心", observation.ui_nodes[1].text)
        self.assertFalse(observation.ui_nodes[1].clickable)
        self.assertEqual("BGR", observation.screenshot.pixel_format)
        self.assertEqual(10, observation.screenshot.width)

    def test_required_ui_tree_failure_is_not_reported_as_success(self):
        self.manager.poco = BrokenPoco()

        result = self.adapter.observe(ObservationRequest(include_ui_tree=True))

        self.assertEqual(ActionStatus.FAILED, result.status)
        self.assertFalse(result.succeeded)
        self.assertFalse(result.retryable)
        self.assertIn("UI 树获取失败", result.message)

    def test_poco_service_activity_falls_back_to_real_foreground_app(self):
        self.manager.dev.activity_output = (
            "topResumedActivity=ActivityRecord{123456 u0 "
            "com.netease.open.pocoservice/.TestActivity t123}"
        )

        result = self.adapter.observe(ObservationRequest(include_ui_tree=False))

        self.assertTrue(result.succeeded)
        self.assertEqual("com.example", result.observation.activity.package_name)
        self.assertEqual("MainActivity", result.observation.activity.activity_name)

    def test_poco_service_activity_uses_recently_started_app_when_fallback_is_transient(self):
        self.adapter.start_app(self.app)
        self.manager.dev.activity_output = (
            "topResumedActivity=ActivityRecord{123456 u0 "
            "com.netease.open.pocoservice/.TestActivity t123}"
        )
        self.manager.top_activity = ("com.netease.open.pocoservice", "TestActivity")

        result = self.adapter.observe(ObservationRequest(include_ui_tree=False))

        self.assertTrue(result.succeeded)
        self.assertEqual("com.example", result.observation.activity.package_name)

    def test_system_key_is_mapped_without_exposing_airtest(self):
        self.adapter.press(SystemKey.SLEEP)

        self.assertEqual(("keyevent", "SLEEP"), self.manager.dev.calls[-1])

    def test_text_input_supports_chinese_without_pressing_enter(self):
        result = self.adapter.input_text("最近怎么样")

        self.assertTrue(result.succeeded)
        self.assertEqual(("text", "最近怎么样", False), self.manager.dev.calls[-1])

    def test_disconnect_keeps_adb_transport_connected(self):
        result = self.adapter.disconnect()

        self.assertTrue(result.succeeded)
        self.assertNotIn(("disconnect",), self.manager.dev.calls)

    def test_system_tree_can_be_selected_per_observation(self):
        result = self.adapter.observe(
            ObservationRequest(ui_tree_source=UiTreeSource.SYSTEM)
        )

        self.assertTrue(result.succeeded)
        node = result.observation.ui_nodes[1]
        self.assertEqual("任务中心", node.text)
        self.assertEqual("com.example:id/task", node.resource_id)
        self.assertAlmostEqual(0.1, node.bounds.left)
        self.assertEqual("system", result.observation.metadata["ui_tree_source"])


if __name__ == "__main__":
    unittest.main()
