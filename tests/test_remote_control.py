import json
import unittest

from hym.adapters.control import HttpRemoteControlClient
from hym.core.config import ReportingSettings
from hym.core.control import DeviceControlState, TaskScope
from hym.runtime.control import RemoteControlCoordinator
from hym.runtime.workflow import StepDefinition, StepOutcome, WorkflowDefinition
from hym.testing import FakeClock


class FakeControlPort:
    def __init__(self, states):
        self.states = list(states)
        self.acknowledged = 0

    def control(self, device_id):
        if len(self.states) > 1:
            return self.states.pop(0)
        return self.states[0]

    def acknowledge_pause(self, device_id):
        self.acknowledged += 1

    def claim_command(self, device_id):
        return None

    def complete_command(self, device_id, command_id, *, succeeded, message):
        return None


class RemoteControlTest(unittest.TestCase):
    def test_client_uses_short_timeout_and_maps_control_response(self):
        requests = []

        def send(method, url, headers, body, timeout):
            requests.append((method, url, headers, body, timeout))
            return 200, json.dumps(
                {
                    "deviceId": "device 1",
                    "pauseRequested": True,
                    "requestedAtMs": 100,
                    "pauseUntilMs": 200,
                }
            ).encode()

        client = HttpRemoteControlClient(
            ReportingSettings(
                enabled=True,
                server_url="http://server",
                ingest_key="secret",
                control_timeout_seconds=0.8,
            ),
            sender=send,
        )

        state = client.control("device 1")

        self.assertTrue(state.pause_requested)
        self.assertIn("/control/device%201", requests[0][1])
        self.assertEqual(0.8, requests[0][4])

    def test_pause_waits_until_manual_resume(self):
        clock = FakeClock()
        now_ms = int(clock.now().timestamp() * 1_000)
        paused = DeviceControlState("device-1", True, now_ms, now_ms + 60_000)
        resumed = DeviceControlState("device-1", False)
        port = FakeControlPort([paused, resumed])
        control = RemoteControlCoordinator(port, "device-1", clock, 5, 30)

        initial = control.poll_pause(force=True)
        reason = control.wait_for_resume(initial)

        self.assertEqual("manual", reason)
        self.assertEqual(1, port.acknowledged)
        self.assertEqual([5], clock.sleeps)

    def test_pause_uses_server_deadline_as_timeout(self):
        clock = FakeClock()
        now_ms = int(clock.now().timestamp() * 1_000)
        paused = DeviceControlState("device-1", True, now_ms, now_ms + 7_000)
        port = FakeControlPort([paused])
        control = RemoteControlCoordinator(port, "device-1", clock, 5, 30)

        reason = control.wait_for_resume(paused)

        self.assertEqual("timeout", reason)
        self.assertEqual([5, 2], clock.sleeps)

    def test_workflow_scope_keeps_setup_and_cleanup_only(self):
        handler = lambda _: StepOutcome.success()
        workflow = WorkflowDefinition(
            "daily",
            "每日任务",
            (
                StepDefinition("启动", "启动", handler, task_scope=TaskScope.SETUP),
                StepDefinition("签到", "签到", handler, task_scope=TaskScope.CHECK_IN),
                StepDefinition("余额", "余额", handler, task_scope=TaskScope.BALANCE),
                StepDefinition("收尾", "收尾", handler, task_scope=TaskScope.CLEANUP),
            ),
        )

        selected = workflow.for_scope(TaskScope.CHECK_IN)

        self.assertEqual(["启动", "签到", "收尾"], [step.step_id for step in selected.steps])
        with self.assertRaisesRegex(ValueError, "不支持"):
            workflow.for_scope(TaskScope.AD_REWARD)


if __name__ == "__main__":
    unittest.main()
