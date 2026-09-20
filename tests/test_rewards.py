import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace

from hym.apps.app_specs import kuaishou_spec, qutoutiao_spec
from hym.apps.app_specs.toutiao_lite import ToutiaoNovelBonusTask
from hym.core.models import ActivityInfo, ImageFrame, Observation, OcrText, Rect, WorkflowStatus
from hym.runtime.context import DailyActionStatus
from hym.runtime.rewards import AdRewardTask, BalanceTask, CheckInTask, DurationRewardTask, WithdrawalTask


class StubActions:
    def __init__(self, *, page_exists: bool = True, reward_exists: bool = True):
        self.page_exists = page_exists
        self.reward_exists = reward_exists
        self.tapped = []

    def tap_target(self, target, timeout=2.0):
        self.tapped.append(target.target_id)
        if target.target_id == "快手奖励广告":
            return False
        return True

    def exists(self, target, timeout=1.0):
        if target.target_id == "快手收益页":
            return self.page_exists
        return self.reward_exists

    def needs_screenshot(self, targets):
        return False


class StubTiming:
    def __init__(self):
        self.waits = []
        self.operation_delays = 0

    def wait(self, seconds):
        self.waits.append(seconds)

    def operation_delay(self):
        self.operation_delays += 1


class StubState:
    def __init__(self):
        self.values = {}

    def get(self, namespace, key, default=None):
        return self.values.get((namespace, key), default)

    def set(self, namespace, key, value):
        self.values[(namespace, key)] = value


def context(actions):
    rewards = []
    return SimpleNamespace(
        actions=actions,
        timing=StubTiming(),
        daily_value=lambda key: None,
        rewards=rewards,
        record_reward=lambda reward_type, message, **data: rewards.append(
            (reward_type, message, data)
        ),
    )


class RewardTaskTest(unittest.TestCase):
    def test_optional_reward_navigation_failures_are_skipped(self):
        events = []
        daily = {}
        current = SimpleNamespace(
            daily_value=lambda key: daily.get(key),
            mark_daily=lambda key, value: daily.__setitem__(key, {"value": value}),
            daily_action_status=lambda key: DailyActionStatus.NOT_STARTED,
            emit=lambda *args, **kwargs: events.append((args, kwargs)),
        )

        outcomes = (
            CheckInTask(kuaishou_spec(), lambda _: False).run(current),
            BalanceTask(kuaishou_spec(), lambda _: False).run(current),
            DurationRewardTask(kuaishou_spec(), lambda _: False).run(current),
        )

        self.assertTrue(all(outcome.status is WorkflowStatus.SKIPPED for outcome in outcomes))
        self.assertEqual(3, len(events))
        self.assertTrue(all(event[0][0] == "reward.optional.unavailable" for event in events))

    def test_toutiao_novel_navigation_failure_is_an_optional_reward(self):
        events = []
        current = SimpleNamespace(
            random=SimpleNamespace(random=lambda: 0.0),
            option=lambda key, default: default,
            emit=lambda *args, **kwargs: events.append((args, kwargs)),
        )

        outcome = ToutiaoNovelBonusTask(lambda _: False).run(current)

        self.assertEqual(WorkflowStatus.SKIPPED, outcome.status)
        self.assertEqual("reward.optional.unavailable", events[0][0][0])
        self.assertEqual("skipped", events[0][1]["status"])

    def test_ad_reward_success_is_not_downgraded_when_later_entry_is_unavailable(self):
        outcome = AdRewardTask._summarize(completed=1, uncertain=0, failed=1, total=2)

        self.assertEqual(WorkflowStatus.SUCCESS, outcome.status)
        self.assertEqual(1, outcome.outputs["completed"])
        self.assertEqual(1, outcome.outputs["failed"])

    def test_ad_reward_with_no_available_entry_is_skipped(self):
        outcome = AdRewardTask._summarize(completed=0, uncertain=0, failed=2, total=2)

        self.assertEqual(WorkflowStatus.SKIPPED, outcome.status)

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

    def test_failed_balance_observation_is_not_retried_the_same_day(self):
        daily = {}
        navigation_calls = []
        current = context(StubActions())
        current.daily_value = lambda key: daily.get(key)
        current.mark_daily = lambda key, value: daily.__setitem__(
            key,
            {"value": value},
        )
        current.emit = lambda *args, **kwargs: None
        task = BalanceTask(
            qutoutiao_spec(),
            lambda _: navigation_calls.append(True) or False,
        )

        first = task.run(current)
        second = task.run(current)

        self.assertEqual(WorkflowStatus.SKIPPED, first.status)
        self.assertEqual(WorkflowStatus.ALREADY_DONE, second.status)
        self.assertEqual([True], navigation_calls)

    def test_duration_reward_reports_unconfirmed_without_follow_up_clicks(self):
        spec = kuaishou_spec()
        actions = StubActions(reward_exists=False)
        current = context(actions)

        outcome = DurationRewardTask(spec, lambda _: True).run(current)

        self.assertEqual(WorkflowStatus.RETRYABLE_FAILURE, outcome.status)
        self.assertEqual([3.0], current.timing.waits)
        self.assertEqual(["快手任务页右下角宝箱"], actions.tapped)
        self.assertEqual([], current.rewards)

    def test_duration_reward_records_only_confirmed_claim(self):
        spec = kuaishou_spec()
        current = context(StubActions())

        outcome = DurationRewardTask(spec, lambda _: True).run(current)

        self.assertEqual(WorkflowStatus.SUCCESS, outcome.status)
        self.assertEqual("duration_reward", current.rewards[0][0])
        self.assertIsNone(spec.duration_reward.ad_target)
        self.assertIsNone(spec.duration_reward.close_target)

    def test_withdrawal_reads_one_screenshot_and_records_structured_amounts(self):
        spec = kuaishou_spec()
        actions = StubActions()
        actions.tap_first = lambda targets, timeout=1.0: None
        actions.press = lambda key: True
        actions.observe = lambda **kwargs: Observation(
            "device-1",
            ActivityInfo(),
            screenshot=ImageFrame(10, 10, b"frame"),
        )
        state = StubState()
        daily = {}
        events = []
        current = SimpleNamespace(
            actions=actions,
            timing=SimpleNamespace(
                wait=lambda seconds: None,
                operation_delay=lambda: None,
                clock=SimpleNamespace(now=lambda: datetime(2026, 9, 19, tzinfo=timezone.utc)),
            ),
            sample_seconds=lambda *args, **kwargs: 0,
            state=state,
            namespace="device-1:kuaishou",
            business_date=date(2026, 9, 19),
            daily_value=lambda key: daily.get(key),
            mark_daily=lambda key, value: daily.__setitem__(key, {"value": value}),
            option=lambda key, default: default,
            random=SimpleNamespace(random=lambda: 0.0),
            ocr=SimpleNamespace(
                recognize=lambda frame: (
                    OcrText("3.20", Rect(0.10, 0.18, 0.25, 0.22), 0.99, "test"),
                    OcrText("0.5元", Rect(0.10, 0.42, 0.25, 0.47), 0.99, "test"),
                    OcrText("连续签到3天", Rect(0.08, 0.48, 0.27, 0.52), 0.99, "test"),
                    OcrText("15元", Rect(0.40, 0.42, 0.55, 0.47), 0.99, "test"),
                    OcrText("需完成实名认证", Rect(0.37, 0.48, 0.61, 0.52), 0.99, "test"),
                    OcrText("30元", Rect(0.70, 0.42, 0.84, 0.47), 0.99, "test"),
                    OcrText("仅限新用户", Rect(0.68, 0.48, 0.88, 0.52), 0.99, "test"),
                )
            ),
            emit=lambda *args, **kwargs: events.append((args, kwargs)),
        )

        outcome = WithdrawalTask(spec, lambda _: True).run(current)

        self.assertEqual(WorkflowStatus.SUCCESS, outcome.status)
        snapshot = state.get(current.namespace, "withdrawal:last")
        self.assertEqual(320, snapshot["available_amount_minor"])
        self.assertEqual(50, snapshot["minimum_amount_minor"])
        self.assertTrue(snapshot["eligible"])
        self.assertEqual([50, 1500, 3000], [tier["amount_minor"] for tier in snapshot["tiers"]])
        self.assertEqual("连续签到3天", snapshot["tiers"][0]["requirement"])
        self.assertEqual("需完成实名认证", snapshot["tiers"][1]["requirement"])
        self.assertEqual("仅限新用户", snapshot["tiers"][2]["requirement"])
        self.assertTrue(snapshot["tiers"][0]["balance_eligible"])
        self.assertFalse(snapshot["tiers"][1]["balance_eligible"])
        self.assertEqual("reward.withdrawal.snapshot", events[0][0][0])

    def test_withdrawal_navigation_failure_is_reported_but_does_not_fail_workflow(self):
        events = []
        daily = {}
        current = SimpleNamespace(
            state=StubState(),
            namespace="device-1:kuaishou",
            business_date=date(2026, 9, 19),
            daily_value=lambda key: daily.get(key),
            mark_daily=lambda key, value: daily.__setitem__(key, {"value": value}),
            option=lambda key, default: default,
            random=SimpleNamespace(random=lambda: 0.0),
            ocr=object(),
            emit=lambda *args, **kwargs: events.append((args, kwargs)),
        )

        outcome = WithdrawalTask(kuaishou_spec(), lambda _: False).run(current)

        self.assertEqual(WorkflowStatus.SKIPPED, outcome.status)
        self.assertEqual("reward.withdrawal.unavailable", events[0][0][0])
        self.assertEqual("skipped", events[0][1]["status"])

    def test_withdrawal_refresh_is_sampled_only_once_per_day(self):
        daily = {}
        random_calls = []
        navigation_calls = []
        current = SimpleNamespace(
            state=StubState(),
            namespace="device-1:kuaishou",
            business_date=date(2026, 9, 19),
            daily_value=lambda key: daily.get(key),
            mark_daily=lambda key, value: daily.__setitem__(key, {"value": value}),
            option=lambda key, default: default,
            random=SimpleNamespace(
                random=lambda: random_calls.append(True) or 0.75,
            ),
            ocr=object(),
            emit=lambda *args, **kwargs: None,
        )
        task = WithdrawalTask(
            kuaishou_spec(),
            lambda _: navigation_calls.append(True) or True,
        )

        first = task.run(current)
        second = task.run(current)

        self.assertEqual(WorkflowStatus.SKIPPED, first.status)
        self.assertEqual(WorkflowStatus.ALREADY_DONE, second.status)
        self.assertEqual([True], random_calls)
        self.assertEqual([], navigation_calls)


if __name__ == "__main__":
    unittest.main()
