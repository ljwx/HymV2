import unittest
from types import SimpleNamespace

from hym.core.config import AppRunSettings, BehaviorSettings, InterruptionSettings
from hym.core.events import InMemoryEventSink
from hym.core.models import ActionResult, AppIdentity, DeviceDescriptor, SystemKey
from hym.runtime.behavior import BehaviorTiming
from hym.runtime.context import AppContext
from hym.runtime.interruption import (
    InterruptionKind,
    InterruptionPolicy,
    InterruptionRequest,
)
from hym.runtime.runner import DeviceWorker, _AppJob
from hym.runtime.workflow import StepDefinition, StepOutcome, WorkflowDefinition, WorkflowExecutor
from hym.testing import FakeClock, InMemoryStateStore


class ScriptedRandom:
    def __init__(self, values):
        self.values = list(values)

    def random(self):
        return self.values.pop(0)

    def uniform(self, start, end):
        return (start + end) / 2

    def normalvariate(self, center, stddev):
        return center

    def randint(self, start, end):
        return start

    def choice(self, items):
        return items[0]


class StubActions:
    def __init__(self):
        self.pressed = []

    def press(self, key):
        self.pressed.append(key)
        return True


class StubSession:
    descriptor = DeviceDescriptor("device-1")


class StubDiagnostics:
    def capture(self, name, observation=None, metadata=None):
        return ()


def _job(app_id):
    events = []
    context = SimpleNamespace(
        actions=StubActions(),
        emit=lambda *args, **kwargs: events.append((args, kwargs)),
    )
    plugin = SimpleNamespace(
        app_id=app_id,
        spec=SimpleNamespace(
            display_name=app_id,
            identity=AppIdentity(app_id, f"com.example.{app_id}", app_id),
        ),
    )
    execution = WorkflowExecutor().create("daily", "每日任务", ())
    return _AppJob(AppRunSettings(app_id), plugin, context, execution), events


class InterruptionPolicyTest(unittest.TestCase):
    def test_policy_respects_interval_and_cycle_limit(self):
        clock = FakeClock()
        policy = InterruptionPolicy(
            InterruptionSettings(
                enabled=True,
                checkpoint_probability=1,
                desktop_pause_probability=0.5,
                min_interval_seconds=60,
                max_per_cycle=2,
            ),
            clock,
            ScriptedRandom([0.0, 0.9, 0.0, 0.1]),
        )

        first = policy.request("step.finished")
        self.assertEqual(InterruptionKind.APP_SWITCH, first.kind)
        self.assertIsNone(policy.request("step.finished"))

        clock.sleep(60)
        second = policy.request("content.item.finished")
        self.assertEqual(InterruptionKind.DESKTOP_PAUSE, second.kind)
        clock.sleep(60)
        self.assertIsNone(policy.request("step.finished"))

    def test_disabled_policy_never_interrupts(self):
        policy = InterruptionPolicy(
            InterruptionSettings(enabled=False),
            FakeClock(),
            ScriptedRandom([]),
        )

        self.assertIsNone(policy.request("step.finished"))


class InterruptionHandlingTest(unittest.TestCase):
    def _worker(self, *, desktop_min=20, desktop_max=60):
        worker = object.__new__(DeviceWorker)
        worker.clock = FakeClock()
        worker.random = ScriptedRandom([])
        worker.settings = SimpleNamespace(
            interruptions=InterruptionSettings(
                desktop_wait_seconds_min=desktop_min,
                desktop_wait_seconds_center=(desktop_min + desktop_max) / 2,
                desktop_wait_seconds_max=desktop_max,
                desktop_wait_seconds_stddev=max((desktop_max - desktop_min) / 6, 0.001),
            )
        )
        return worker

    def test_app_switch_selects_another_pending_job(self):
        worker = self._worker()
        current, events = _job("kuaishou")
        target, _ = _job("douyin")

        selected = worker._handle_interruption(
            [current, target],
            0,
            InterruptionRequest(InterruptionKind.APP_SWITCH, "step.finished"),
        )

        self.assertEqual(1, selected)
        self.assertEqual("runtime.interruption.app_switch", events[0][0][0])

    def test_app_switch_falls_back_to_desktop_when_no_other_job(self):
        worker = self._worker(desktop_min=30, desktop_max=30)
        current, events = _job("kuaishou")

        selected = worker._handle_interruption(
            [current],
            0,
            InterruptionRequest(InterruptionKind.APP_SWITCH, "content.item.finished"),
        )

        self.assertEqual(0, selected)
        self.assertEqual([SystemKey.HOME], current.context.actions.pressed)
        self.assertEqual([30], worker.clock.sleeps)
        self.assertEqual(
            [
                "runtime.interruption.desktop.started",
                "runtime.interruption.desktop.finished",
            ],
            [event[0][0] for event in events],
        )


class CycleCleanupTest(unittest.TestCase):
    def test_stops_cycle_apps_before_locking_screen(self):
        operations = []
        session = SimpleNamespace(
            stop_app=lambda app: (
                operations.append(("stop_app", app.app_id))
                or ActionResult.success("stop_app")
            ),
            press=lambda key: (
                operations.append(("press", key))
                or ActionResult.success("press")
            ),
        )
        worker = object.__new__(DeviceWorker)
        worker.session = session
        events = []
        worker._emit_worker_event = lambda *args, **kwargs: events.append((args, kwargs))
        first, _ = _job("kuaishou")
        second, _ = _job("douyin")

        issues = worker._finish_cycle([first, second], "cycle-1")

        self.assertEqual(0, issues)
        self.assertEqual(
            [
                ("stop_app", "kuaishou"),
                ("stop_app", "douyin"),
                ("press", SystemKey.SLEEP),
            ],
            operations,
        )
        self.assertEqual("runtime.cycle.cleanup.finished", events[0][0][1])
        self.assertEqual("success", events[0][1]["status"])


class DeviceWorkerSchedulingTest(unittest.TestCase):
    def test_worker_switches_apps_and_resumes_original_cursor(self):
        operations = []
        app_settings = (AppRunSettings("a1"), AppRunSettings("a2"))
        plugins = {
            app_id: self._plugin(app_id, operations)
            for app_id in ("a1", "a2")
        }
        clock = FakeClock()
        random_source = ScriptedRandom([0.0, 0.9])
        state = InMemoryStateStore()
        events = InMemoryEventSink()
        contexts = {
            setting.app_id: AppContext(
                app=plugins[setting.app_id].spec.identity,
                settings=setting,
                session=StubSession(),
                timing=BehaviorTiming(BehaviorSettings(), clock, random_source),
                random_source=random_source,
                state=state,
                events=events,
                diagnostics=StubDiagnostics(),
            )
            for setting in app_settings
        }
        worker = object.__new__(DeviceWorker)
        worker.settings = SimpleNamespace(
            interruptions=InterruptionSettings(
                enabled=True,
                checkpoint_probability=1,
                desktop_pause_probability=0,
                min_interval_seconds=0,
                max_per_cycle=1,
            )
        )
        worker.device_settings = SimpleNamespace(apps=app_settings)
        worker.registry = SimpleNamespace(get=plugins.get)
        worker.clock = clock
        worker.random = random_source
        worker._create_context = (
            lambda trace_id, setting, plugin: contexts[setting.app_id]
        )
        worker._finish_app = lambda context, app: None
        worker._finish_cycle = lambda jobs, trace_id: 0
        cycle_events = []
        worker._emit_worker_event = (
            lambda *args, **kwargs: cycle_events.append((args, kwargs))
        )

        worker._run_cycle()

        self.assertEqual(
            [("a1", "步骤1"), ("a2", "步骤1"), ("a2", "步骤2"), ("a1", "步骤2")],
            operations,
        )
        for context in contexts.values():
            cursor = state.get(context.namespace, "runtime:workflow_cursor")
            self.assertEqual("completed", cursor["status"])
            self.assertEqual(2, cursor["next_index"])
        self.assertEqual("success", cycle_events[-1][1]["status"])

    @staticmethod
    def _plugin(app_id, operations):
        identity = AppIdentity(app_id, f"com.example.{app_id}", app_id)

        def step(step_id):
            def run(_):
                operations.append((app_id, step_id))
                return StepOutcome.success("完成")

            return StepDefinition(step_id, step_id, run)

        return SimpleNamespace(
            app_id=app_id,
            spec=SimpleNamespace(identity=identity, display_name=app_id),
            build_workflow=lambda context: WorkflowDefinition(
                "daily",
                "每日任务",
                (step("步骤1"), step("步骤2")),
            ),
        )


if __name__ == "__main__":
    unittest.main()
