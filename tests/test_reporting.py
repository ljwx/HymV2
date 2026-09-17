import json
import tempfile
import unittest
from pathlib import Path

from hym.adapters.reporting import DurableHttpEventSink
from hym.core.config import ReportingSettings
from hym.core.events import AutomationEvent
from hym.core.models import AppIdentity, ArtifactRef, DeviceDescriptor


class DurableHttpEventSinkTest(unittest.TestCase):
    def test_cycle_finish_uploads_batch_and_removes_queue(self):
        requests = []

        def send(method, url, headers, body):
            requests.append((method, url, headers, body))
            return b"{}"

        with tempfile.TemporaryDirectory() as directory:
            queue = Path(directory) / "queue.jsonl"
            sink = self._sink(queue, send)
            sink.emit(self._event("event-1", "step.finished"))
            self.assertTrue(queue.exists())

            sink.emit(self._event("event-2", "runtime.cycle.finished", app=False))

            self.assertFalse(queue.exists())
            payload = json.loads(requests[0][3])
            self.assertEqual(["event-1", "event-2"], [item["event_id"] for item in payload["events"]])
            self.assertEqual("device-1", payload["device"]["device_id"])
            self.assertEqual("抖音极速版", payload["apps"][0]["display_name"])

    def test_failed_upload_keeps_queue_for_next_sink(self):
        attempts = 0

        def fail_once(method, url, headers, body):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("服务器离线")
            return b"{}"

        with tempfile.TemporaryDirectory() as directory:
            queue = Path(directory) / "queue.jsonl"
            first = self._sink(queue, fail_once)
            first.emit(self._event("event-1", "runtime.cycle.finished", app=False))
            self.assertTrue(queue.exists())

            second = self._sink(queue, fail_once)
            second.flush()

            self.assertFalse(queue.exists())
            self.assertEqual(2, attempts)

    def test_failed_upload_uses_backoff_instead_of_retrying_each_event(self):
        attempts = 0

        def fail(method, url, headers, body):
            nonlocal attempts
            attempts += 1
            raise RuntimeError("服务器离线")

        with tempfile.TemporaryDirectory() as directory:
            queue = Path(directory) / "queue.jsonl"
            sink = self._sink(queue, fail)
            for index in range(12):
                sink.emit(self._event(f"event-{index}", "step.progress"))

            self.assertEqual(1, attempts)
            self.assertEqual(12, len(queue.read_text(encoding="utf-8").splitlines()))

    def test_events_before_cycle_are_local_only(self):
        requests = []

        with tempfile.TemporaryDirectory() as directory:
            queue = Path(directory) / "queue.jsonl"
            sink = self._sink(queue, lambda *args: requests.append(args) or b"{}")
            sink.emit(
                AutomationEvent(
                    event_type="device.connect.succeeded",
                    trace_id="trace-1",
                    device_id="device-1",
                    event_id="connect-1",
                )
            )

            self.assertFalse(queue.exists())
            self.assertEqual([], requests)

    def test_flush_discards_legacy_events_without_cycle(self):
        requests = []

        def send(method, url, headers, body):
            requests.append((method, url, headers, body))
            return b"{}"

        with tempfile.TemporaryDirectory() as directory:
            queue = Path(directory) / "queue.jsonl"
            queue.write_text(
                json.dumps(
                    {
                        "event_id": "connect-1",
                        "event_type": "device.connect.succeeded",
                        "cycle_id": None,
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "event_id": "event-1",
                        "event_type": "runtime.cycle.finished",
                        "cycle_id": "cycle-1",
                        "artifacts": [],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            self._sink(queue, send).flush()

            self.assertFalse(queue.exists())
            payload = json.loads(requests[0][3])
            self.assertEqual(["event-1"], [item["event_id"] for item in payload["events"]])

    def test_uploads_existing_artifact_after_event_metadata(self):
        requests = []

        def send(method, url, headers, body):
            requests.append((method, url, headers, body))
            return b"{}"

        with tempfile.TemporaryDirectory() as directory:
            artifact_path = Path(directory) / "screen.png"
            artifact_path.write_bytes(b"png")
            queue = Path(directory) / "queue.jsonl"
            sink = self._sink(queue, send)
            event = self._event("event-1", "runtime.cycle.finished", app=False)
            event = AutomationEvent(
                event_type=event.event_type,
                trace_id=event.trace_id,
                device_id=event.device_id,
                event_id=event.event_id,
                cycle_id=event.cycle_id,
                artifacts=(
                    ArtifactRef(
                        artifact_id="artifact-1",
                        kind="页面截图",
                        uri=str(artifact_path),
                        media_type="image/png",
                    ),
                ),
            )

            sink.emit(event)

            self.assertEqual(["POST", "PUT"], [item[0] for item in requests])
            self.assertTrue(requests[1][1].endswith("/artifact-1"))
            self.assertEqual(b"png", requests[1][3])

    @staticmethod
    def _sink(queue, sender):
        return DurableHttpEventSink(
            ReportingSettings(
                enabled=True,
                server_url="http://server",
                ingest_key="secret",
                batch_size=10,
            ),
            queue,
            DeviceDescriptor("device-1", model="测试手机"),
            (AppIdentity("douyin", "com.example", "抖音极速版"),),
            sender=sender,
        )

    @staticmethod
    def _event(event_id, event_type, *, app=True):
        return AutomationEvent(
            event_type=event_type,
            trace_id="trace-1",
            device_id="device-1",
            event_id=event_id,
            cycle_id="cycle-1",
            app_run_id="run-1" if app else None,
            app_id="douyin" if app else None,
            status="success",
        )


if __name__ == "__main__":
    unittest.main()
