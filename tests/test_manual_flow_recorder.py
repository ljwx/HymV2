import json
import tempfile
import unittest
from pathlib import Path

from hym.core.models import (
    ActionStatus,
    ActivityInfo,
    DeviceDescriptor,
    Observation,
    ObservationResult,
    UiNode,
)
from hym.runtime.recorder import ManualFlowRecorder
from hym.testing import FakeClock


class StubSession:
    descriptor = DeviceDescriptor("device-1")

    def __init__(self, observations):
        self._clock = FakeClock()
        self.observations = iter(observations)

    def observe(self, request):
        return ObservationResult(ActionStatus.SUCCESS, next(self.observations))


class StubDiagnostics:
    def __init__(self):
        self.captures = []

    def capture(self, name, observation, metadata):
        self.captures.append((name, observation, metadata))
        return ()


class ManualFlowRecorderTest(unittest.TestCase):
    def test_records_action_and_page_transition(self):
        before = Observation(
            "device-1",
            ActivityInfo("com.example", "HomeActivity"),
            ui_nodes=(UiNode("1", None, resource_id="com.example:id/home"),),
        )
        after = Observation(
            "device-1",
            ActivityInfo("com.example", "RewardActivity"),
            ui_nodes=(UiNode("2", None, text="立即领取", clickable=True),),
        )
        diagnostics = StubDiagnostics()
        commands = iter(("点击奖励入口", ":done"))
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manifest.json"
            recorder = ManualFlowRecorder(
                session=StubSession((before, after)),
                diagnostics=diagnostics,
                manifest_path=manifest_path,
                flow_name="新奖励",
                input_fn=lambda prompt: next(commands),
                output_fn=lambda message: None,
            )

            result = recorder.run()
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(0, result)
        self.assertEqual("completed", manifest["status"])
        self.assertEqual("点击奖励入口", manifest["steps"][0]["action_note"])
        self.assertTrue(manifest["steps"][0]["transition"]["activity_changed"])
        self.assertIn("text:立即领取", manifest["steps"][0]["transition"]["added_markers"])
        self.assertEqual(2, len(diagnostics.captures))


if __name__ == "__main__":
    unittest.main()
