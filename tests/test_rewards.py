import unittest
from types import SimpleNamespace

from hym.apps.app_specs import kuaishou_spec, qutoutiao_spec
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
    def test_kuaishou_balance_reads_both_assets_from_task_page(self):
        spec = kuaishou_spec()
        balance = spec.balance

        self.assertIsNotNone(balance)
        self.assertIsNone(balance.enter_target)
        self.assertEqual(["coin", "cash"], [asset.asset_key for asset in balance.assets])

    def test_single_value_balance_is_not_recorded_twice(self):
        actions = StubActions()
        current = context(actions)
        current.daily_value = lambda _: {
            "value": {"value": "约0.0元", "artifacts": []},
            "recorded_at": "2026-09-17T12:00:00+08:00",
        }

        outcome = BalanceTask(qutoutiao_spec(), lambda _: False).run(current)

        self.assertEqual(WorkflowStatus.ALREADY_DONE, outcome.status)

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
