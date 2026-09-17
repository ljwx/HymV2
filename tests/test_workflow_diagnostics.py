import unittest

from hym.core.config import AppRunSettings, BehaviorSettings
from hym.core.events import InMemoryEventSink
from hym.core.models import AppIdentity, DeviceDescriptor, WorkflowStatus
from hym.runtime.behavior import BehaviorTiming
from hym.runtime.context import AppContext
from hym.runtime.interruption import InterruptionKind, InterruptionRequest, WorkflowYield
from hym.runtime.workflow import StepDefinition, StepOutcome, WorkflowExecutor
from hym.testing import DeterministicRandom, FakeClock, InMemoryStateStore


class StubSession:
    descriptor = DeviceDescriptor("device-1")


class StubDiagnostics:
    def __init__(self):
        self.calls = []

    def capture(self, name, observation=None, metadata=None):
        self.calls.append((name, metadata))
        return ()


class WorkflowDiagnosticsTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.random = DeterministicRandom()
        self.state = InMemoryStateStore()
        self.events = InMemoryEventSink()
        self.diagnostics = StubDiagnostics()
        self.context = AppContext(
            app=AppIdentity("app", "com.example", "示例"),
            settings=AppRunSettings("app"),
            session=StubSession(),
            timing=BehaviorTiming(BehaviorSettings(), self.clock, self.random),
            random_source=self.random,
            state=self.state,
            events=self.events,
            diagnostics=self.diagnostics,
            diagnostic_failure_threshold=3,
        )

    def test_captures_only_after_three_consecutive_failures(self):
        step = StepDefinition("关键步骤", "关键步骤", lambda _: StepOutcome.failure("没有找到入口"))

        for _ in range(2):
            WorkflowExecutor().run(self.context, "daily", "每日任务", [step])
        self.assertEqual([], self.diagnostics.calls)

        WorkflowExecutor().run(self.context, "daily", "每日任务", [step])

        self.assertEqual(1, len(self.diagnostics.calls))
        self.assertEqual(3, self.diagnostics.calls[0][1]["consecutive_failure_count"])

        for _ in range(3):
            WorkflowExecutor().run(self.context, "daily", "每日任务", [step])
        self.assertEqual(1, len(self.diagnostics.calls))

    def test_partial_step_makes_workflow_partial(self):
        step = StepDefinition(
            "广告",
            "广告",
            lambda _: StepOutcome(WorkflowStatus.PARTIAL, "部分完成"),
        )

        result = WorkflowExecutor().run(self.context, "daily", "每日任务", [step])

        self.assertEqual(WorkflowStatus.PARTIAL, result.status)

    def test_success_resets_failure_counter(self):
        failure = StepDefinition("关键步骤", "关键步骤", lambda _: StepOutcome.failure("失败"))
        success = StepDefinition("关键步骤", "关键步骤", lambda _: StepOutcome.success("成功"))
        WorkflowExecutor().run(self.context, "daily", "每日任务", [failure])
        WorkflowExecutor().run(self.context, "daily", "每日任务", [success])
        WorkflowExecutor().run(self.context, "daily", "每日任务", [failure])

        value = self.state.get(self.context.namespace, "failure:daily:关键步骤")
        self.assertEqual(1, value["count"])

    def test_different_failure_reason_starts_a_new_sequence(self):
        first = StepDefinition("关键步骤", "关键步骤", lambda _: StepOutcome.failure("入口缺失"))
        second = StepDefinition("关键步骤", "关键步骤", lambda _: StepOutcome.failure("页面错误"))
        WorkflowExecutor().run(self.context, "daily", "每日任务", [first])
        WorkflowExecutor().run(self.context, "daily", "每日任务", [first])
        WorkflowExecutor().run(self.context, "daily", "每日任务", [second])

        value = self.state.get(self.context.namespace, "failure:daily:关键步骤")
        self.assertEqual(1, value["count"])
        self.assertEqual([], self.diagnostics.calls)

    def test_step_events_include_parent_child_trace_ids(self):
        context = AppContext(
            app=AppIdentity("app", "com.example", "示例"),
            settings=AppRunSettings("app"),
            session=StubSession(),
            timing=BehaviorTiming(BehaviorSettings(), self.clock, self.random),
            random_source=self.random,
            state=self.state,
            events=self.events,
            diagnostics=self.diagnostics,
            cycle_id="cycle-1",
            app_run_id="app-run-1",
        )
        WorkflowExecutor().run(
            context,
            "daily",
            "每日任务",
            [StepDefinition("步骤", "步骤", lambda _: StepOutcome.success("完成"))],
        )

        step_events = [event for event in self.events.events if event.event_type.startswith("step.")]
        self.assertTrue(step_events)
        self.assertTrue(all(event.cycle_id == "cycle-1" for event in step_events))
        self.assertTrue(all(event.app_run_id == "app-run-1" for event in step_events))
        self.assertTrue(all(event.step_run_id for event in step_events))

    def test_safe_pause_keeps_cursor_on_current_step(self):
        calls = 0

        def handler(_):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise WorkflowYield(
                    InterruptionRequest(
                        InterruptionKind.APP_SWITCH,
                        "content.item.finished",
                        {"index": 1},
                    )
                )
            return StepOutcome.success("恢复后完成")

        executor = WorkflowExecutor()
        execution = executor.create(
            "daily",
            "每日任务",
            [StepDefinition("浏览内容", "浏览内容", handler)],
        )

        with self.assertRaises(WorkflowYield) as raised:
            executor.run_next(self.context, execution)

        self.assertEqual(0, execution.next_index)
        self.assertEqual([], execution.results)
        self.assertIsNone(self.context.step_run_id)
        executor.suspend(self.context, execution, raised.exception.request)
        cursor = self.state.get(self.context.namespace, "runtime:workflow_cursor")
        self.assertEqual("suspended", cursor["status"])
        self.assertEqual("浏览内容", cursor["next_step_id"])

        executor.resume(self.context, execution)
        executor.run_next(self.context, execution)
        result = executor.finish(self.context, execution)

        self.assertEqual(WorkflowStatus.SUCCESS, result.status)
        self.assertEqual(2, calls)
        cursor = self.state.get(self.context.namespace, "runtime:workflow_cursor")
        self.assertEqual("completed", cursor["status"])
        self.assertEqual(1, cursor["next_index"])


if __name__ == "__main__":
    unittest.main()
