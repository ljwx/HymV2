import json
import io
import tempfile
import unittest
from pathlib import Path

from hym.adapters.events import ConsoleEventSink, JsonlEventSink
from hym.core.events import AutomationEvent, EventFilter, EventLevel, to_jsonable


class JsonlEventSinkTest(unittest.TestCase):
    def test_writes_versioned_unicode_event(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            sink = JsonlEventSink(path)
            event = AutomationEvent(
                event_type="step.finished",
                trace_id="trace-1",
                device_id="device-1",
                app_id="kuaishou",
                status="success",
                message="签到完成",
                data={"message": "签到完成"},
            )

            sink.emit(event)

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("1.0", payload["schema_version"])
            self.assertEqual("签到完成", payload["data"]["message"])
            self.assertEqual("签到完成", payload["message"])

    def test_binary_data_must_be_saved_as_artifact(self):
        with self.assertRaises(TypeError):
            to_jsonable({"screenshot": b"raw"})

    def test_jsonl_filter_skips_debug_event(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            sink = JsonlEventSink(path, EventFilter(min_level=EventLevel.INFO))

            sink.emit(
                AutomationEvent(
                    event_type="ad.state.changed",
                    trace_id="trace-1",
                    device_id="device-1",
                    level=EventLevel.DEBUG,
                )
            )

            self.assertFalse(path.exists())

    def test_console_log_is_chinese_and_filterable(self):
        output = io.StringIO()
        sink = ConsoleEventSink(
            EventFilter(min_level=EventLevel.INFO, app_ids=("kuaishou",)),
            stream=output,
        )
        sink.emit(
            AutomationEvent(
                event_type="step.finished",
                event_name="步骤完成",
                trace_id="trace-1",
                device_id="device-1",
                app_id="kuaishou",
                step_id="check_in",
                status="success",
                message="签到完成",
            )
        )
        sink.emit(
            AutomationEvent(
                event_type="locator.candidate",
                event_name="定位候选",
                trace_id="trace-1",
                device_id="device-1",
                app_id="douyin",
                level=EventLevel.DEBUG,
                message="候选节点",
            )
        )

        text = output.getvalue()
        self.assertIn("级别=信息", text)
        self.assertIn("事件=步骤完成", text)
        self.assertIn("事件码=step.finished", text)
        self.assertIn("结果=成功", text)
        self.assertNotIn("结果=success", text)
        self.assertIn("消息=\"签到完成\"", text)
        self.assertNotIn("候选节点", text)

    def test_console_translates_waiting_status(self):
        output = io.StringIO()
        sink = ConsoleEventSink(stream=output)

        sink.emit(
            AutomationEvent(
                event_type="navigation.activity.waiting",
                event_name="等待启动页面",
                trace_id="trace-1",
                device_id="device-1",
                status="waiting",
            )
        )

        self.assertIn("结果=等待中", output.getvalue())


if __name__ == "__main__":
    unittest.main()
