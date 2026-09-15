import unittest
from types import SimpleNamespace

from hym.apps.app_specs import kuaishou_spec
from hym.core.models import WorkflowStatus
from hym.runtime.rewards import BalanceTask, DurationRewardTask


class StubActions:
    def __init__(self, *, page_exists: bool = True, reward_exists: bool = True):
        self.page_exists = page_exists
        self.reward_exists = reward_exists
        self.tapped = []

    def tap_target(self, target, timeout=2.0):
        self.tapped.append(target.target_id)
        return True

    def exists(self, target, timeout=1.0):
        if target.target_id == "快手收益页":
            return self.page_exists
        return self.reward_exists


class StubTiming:
    def __init__(self):
        self.waits = []
        self.operation_delays = 0

    def wait(self, seconds):
        self.waits.append(seconds)

    def operation_delay(self):
        self.operation_delays += 1


def context(actions):
    return SimpleNamespace(
        actions=actions,
        timing=StubTiming(),
        daily_value=lambda key: None,
    )


class RewardTaskTest(unittest.TestCase):
    def test_balance_uses_app_specific_page_wait(self):
        spec = kuaishou_spec()
        actions = StubActions(page_exists=False)
        current = context(actions)

        outcome = BalanceTask(spec, lambda _: True).run(current)

        self.assertEqual(WorkflowStatus.RETRYABLE_FAILURE, outcome.status)
        self.assertEqual([4.0], current.timing.waits)
        self.assertEqual(0, current.timing.operation_delays)

    def test_duration_reward_cleans_popup_after_unconfirmed_result(self):
        spec = kuaishou_spec()
        actions = StubActions(reward_exists=False)
        current = context(actions)

        outcome = DurationRewardTask(spec, lambda _: True).run(current)

        self.assertEqual(WorkflowStatus.RETRYABLE_FAILURE, outcome.status)
        self.assertEqual([4.0], current.timing.waits)
        self.assertEqual(
            ["快手时段奖励", "快手时段奖励关闭"],
            actions.tapped,
        )


if __name__ == "__main__":
    unittest.main()
