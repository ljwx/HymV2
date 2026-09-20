import json
import unittest

from hym.adapters.control import HttpRemoteControlClient
from hym.core.config import ReportingSettings
from hym.core.control import DeviceControlState, RemoteCommand, TaskScope
from hym.runtime.control import DeviceControlRuntime, RemoteControlCoordinator
from hym.runtime.workflow import StepDefinition, StepOutcome, WorkflowDefinition
from hym.testing import FakeClock


class FakeControlPort:
    def __init__(self, states):
        self.states = list(states)
        self.acknowledged = 0
        self.completed = []
        self.reported = []

    def control(self, device_id):
        if len(self.states) > 1:
            return self.states.pop(0)
        return self.states[0]

    def acknowledge_pause(self, device_id):
        self.acknowledged += 1

    def report_state(self, device_id, state):
        self.reported.append((device_id, state))

    def claim_command(self, device_id):
        return None

    def complete_command(self, device_id, command_id, *, succeeded, message):
        self.completed.append((device_id, command_id, succeeded, message))


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

    def test_control_poll_reuses_last_state_between_network_polls(self):
        stopped = DeviceControlState("device-1", False, desired_state="stopped")
        port = FakeControlPort([stopped])
        control = RemoteControlCoordinator(port, "device-1", FakeClock(), 10, 30)

        first = control.poll_control(force=True)
        cached = control.poll_control()

        self.assertIs(first, cached)
        self.assertEqual("stopped", cached.desired_state)

    def test_client_maps_device_setting_value(self):
        def send(method, url, headers, body, timeout):
            return 200, json.dumps(
                {
                    "id": "command-1",
                    "deviceId": "device-1",
                    "scope": "device_volume",
                    "rounds": 1,
                    "value": 65,
                }
            ).encode()

        client = HttpRemoteControlClient(
            ReportingSettings(enabled=True, server_url="http://server", ingest_key="secret"),
            sender=send,
        )

        command = client.claim_command("device-1")

        self.assertEqual(TaskScope.DEVICE_VOLUME, command.scope)
        self.assertEqual(65, command.value)

    def test_client_reports_observed_device_state(self):
        requests = []

        def send(method, url, headers, body, timeout):
            requests.append((method, url, json.loads(body)))
            return 200, b"{}"

        client = HttpRemoteControlClient(
            ReportingSettings(enabled=True, server_url="http://server", ingest_key="secret"),
            sender=send,
        )
        client.report_state("device-1", "stopped")

        self.assertEqual(("POST", "http://server/api/v1/automation/ingest/control/device-1/state", {"state": "stopped"}), requests[0])

    def test_device_setting_command_runs_without_workflow(self):
        class Session:
            def __init__(self):
                self.values = []
                self.closed = False

            def connect(self):
                return True

            def set_media_volume(self, value):
                self.values.append(value)
                from hym.core.models import ActionResult
                return ActionResult.success("set_media_volume")

            def close(self):
                self.closed = True

        port = FakeControlPort([DeviceControlState("device-1", False)])
        coordinator = RemoteControlCoordinator(port, "device-1", FakeClock(), 5, 30)
        runtime = DeviceControlRuntime(coordinator, lambda *args, **kwargs: None)
        session = Session()

        runtime.run_command(
            RemoteCommand(
                "command-1",
                "device-1",
                None,
                TaskScope.DEVICE_VOLUME,
                1,
                65,
            ),
            session=session,
            run_cycle=lambda **kwargs: self.fail("设备设置不应执行应用工作流"),
            loop_interval_seconds=1,
        )

        self.assertEqual([65], session.values)
        self.assertTrue(session.closed)
        self.assertEqual(("device-1", "command-1", True, "媒体音量已设置为 65%"), port.completed[-1])

    def test_device_home_command_uses_shared_command_channel(self):
        class Session:
            def __init__(self):
                self.keys = []

            def connect(self):
                return True

            def press(self, key):
                self.keys.append(key)
                from hym.core.models import ActionResult
                return ActionResult.success("press")

            def close(self):
                pass

        port = FakeControlPort([DeviceControlState("device-1", False)])
        runtime = DeviceControlRuntime(
            RemoteControlCoordinator(port, "device-1", FakeClock(), 10, 30),
            lambda *args, **kwargs: None,
        )
        session = Session()
        runtime.run_command(
            RemoteCommand("command-home", "device-1", None, TaskScope.DEVICE_HOME, 1),
            session=session,
            run_cycle=lambda **kwargs: self.fail("设备动作不应执行应用工作流"),
            loop_interval_seconds=1,
        )

        from hym.core.models import SystemKey
        self.assertEqual([SystemKey.HOME], session.keys)
        self.assertEqual(("device-1", "command-home", True, "已返回桌面"), port.completed[-1])

    def test_stop_during_workflow_does_not_start_later_rounds(self):
        session = type(
            "Session",
            (),
            {
                "connect": lambda self: True,
                "close": lambda self: None,
            },
        )()
        port = FakeControlPort([DeviceControlState("device-1", False)])
        runtime = DeviceControlRuntime(
            RemoteControlCoordinator(port, "device-1", FakeClock(), 10, 30),
            lambda *args, **kwargs: None,
        )
        calls = []

        runtime.run_command(
            RemoteCommand("command-full", "device-1", None, TaskScope.FULL, 3),
            session=session,
            run_cycle=lambda **kwargs: calls.append(kwargs) or "cancelled",
            loop_interval_seconds=60,
        )

        self.assertEqual(1, len(calls))
        self.assertEqual([], runtime.coordinator.clock.sleeps)
        self.assertEqual(
            ("device-1", "command-full", False, "任务已按停止指令终止"),
            port.completed[-1],
        )

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
