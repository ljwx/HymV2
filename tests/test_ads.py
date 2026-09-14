import unittest
from types import SimpleNamespace

from hym.apps.specs import AdSpec
from hym.apps.targets import coordinate_locator, target
from hym.core.models import ActivityInfo, Observation, Point, SystemKey, WorkflowStatus
from hym.core.targets import ResolveResult, ResolveStatus, ResolvedTarget
from hym.runtime.ads import AdStateMachine
from hym.testing import FakeClock


def _found(target_spec, observation_id="observation"):
    return ResolveResult(
        ResolveStatus.FOUND,
        ResolvedTarget(
            target_spec.target_id,
            target_spec.locators[0].strategy_id,
            Point(0.5, 0.5),
            1.0,
            observation_id,
        ),
    )


class StubTiming:
    def __init__(self):
        self.waits = []
        self.operation_delays = 0
        self.clock = FakeClock()

    def baseline_seconds(self, seconds, *, reward_wait=False):
        return seconds

    def range_seconds(
        self,
        minimum,
        maximum,
        *,
        center=None,
        stddev=None,
        reward_wait=False,
    ):
        return (minimum + maximum) / 2 if center is None else center

    def wait(self, seconds, *, reward_wait=False):
        self.waits.append((seconds, reward_wait))
        self.clock.sleep(seconds)
        return seconds

    def operation_delay(self):
        self.operation_delays += 1


class StubActions:
    def __init__(self, start_target, exit_target, *, always_on_ad=False):
        self.start_target = start_target
        self.exit_target = exit_target
        self.always_on_ad = always_on_ad
        self.observation_count = 0
        self.pressed = []
        self.screenshot_requests = []

    def needs_screenshot(self, targets):
        return False

    def resolve_many(self, targets, *, include_screenshot=False):
        self.screenshot_requests.append(include_screenshot)
        if targets and targets[0].target_id == self.start_target.target_id:
            return self.start_target, _found(self.start_target)
        return None

    def observe(self, *, include_ui_tree, include_screenshot):
        self.observation_count += 1
        self.screenshot_requests.append(include_screenshot)
        return Observation("device-1", ActivityInfo("com.example", "AdActivity"))

    def resolve_in(self, target_spec, observation):
        if target_spec.target_id == self.start_target.target_id:
            if self.always_on_ad or self.observation_count == 1:
                return _found(target_spec, observation.observation_id)
        if target_spec.target_id == self.exit_target.target_id:
            if not self.always_on_ad and self.observation_count >= 2:
                return _found(target_spec, observation.observation_id)
        return ResolveResult(ResolveStatus.NOT_FOUND)

    def tap_first(self, targets, *, timeout):
        return None

    def exists(self, target_spec, timeout):
        return False

    def tap_target(self, target_spec, timeout):
        return False

    def press(self, key):
        self.pressed.append(key)
        return True


class ExitPromptActions:
    def __init__(
        self,
        start_target,
        prompt_target,
        prompt_close_target,
        exit_target,
        prompt_continue_target=None,
    ):
        self.start_target = start_target
        self.prompt_target = prompt_target
        self.prompt_close_target = prompt_close_target
        self.prompt_continue_target = prompt_continue_target
        self.exit_target = exit_target
        self.state = "ad"
        self.pressed = []
        self.clicked = []

    def needs_screenshot(self, targets):
        return False

    def resolve_many(self, targets, *, include_screenshot=False):
        for target_spec in targets:
            if self._visible(target_spec):
                return target_spec, _found(target_spec)
        return None

    def observe(self, *, include_ui_tree, include_screenshot):
        return Observation("device-1", ActivityInfo("com.example", "AdActivity"))

    def resolve_in(self, target_spec, observation):
        if self._visible(target_spec):
            return _found(target_spec, observation.observation_id)
        return ResolveResult(ResolveStatus.NOT_FOUND)

    def tap_first(self, targets, *, timeout):
        if (
            self.state == "prompt"
            and self.prompt_continue_target is not None
            and self.prompt_continue_target in targets
        ):
            self.clicked.append(self.prompt_continue_target.target_id)
            self.state = "ad"
            return self.prompt_continue_target, _found(self.prompt_continue_target)
        if self.state == "prompt" and self.prompt_close_target in targets:
            self.clicked.append(self.prompt_close_target.target_id)
            self.state = "exit"
            return self.prompt_close_target, _found(self.prompt_close_target)
        return None

    def exists(self, target_spec, timeout):
        return False

    def tap_target(self, target_spec, timeout):
        return False

    def press(self, key):
        self.pressed.append(key)
        if self.state == "ad" and key is SystemKey.BACK:
            self.state = "prompt"
        return True

    def _visible(self, target_spec):
        return (
            (self.state == "ad" and target_spec == self.start_target)
            or (self.state == "prompt" and target_spec == self.prompt_target)
            or (self.state == "exit" and target_spec == self.exit_target)
        )


class CompletionExitPromptActions(ExitPromptActions):
    def __init__(self, *args, completion_target, completion_after_checks, **kwargs):
        super().__init__(*args, **kwargs)
        self.completion_target = completion_target
        self.completion_after_checks = completion_after_checks
        self.completion_checks = 0

    def resolve_many(self, targets, *, include_screenshot=False):
        if self.completion_target in targets:
            self.completion_checks += 1
            if self.completion_checks >= self.completion_after_checks:
                return self.completion_target, _found(self.completion_target)
            return None
        return super().resolve_many(targets, include_screenshot=include_screenshot)


class AdStateMachineTest(unittest.TestCase):
    def setUp(self):
        self.start_target = target("广告开始", coordinate_locator("开始坐标", Point(0.5, 0.5)))
        self.exit_target = target("任务页面", coordinate_locator("任务坐标", Point(0.5, 0.5)))
        self.spec = AdSpec(
            start_markers=(self.start_target,),
            continue_targets=(),
            next_sequences=(),
            close_targets=(),
            final_close_targets=(),
            exit_targets=(self.exit_target,),
            completion_wait_seconds=35,
            entry_attempts=1,
            max_cycles=2,
            max_back_attempts=1,
        )

    def _context(self, actions):
        events = []
        return SimpleNamespace(
            actions=actions,
            timing=StubTiming(),
            random=SimpleNamespace(randint=lambda minimum, maximum: maximum),
            sample_count=lambda prefix, minimum, maximum, **kwargs: maximum,
            option=lambda key, default: default,
            emit=lambda *args, **kwargs: events.append((args, kwargs)),
            events=events,
        )

    def test_returns_success_after_recovering_to_exit_page(self):
        actions = StubActions(self.start_target, self.exit_target)
        context = self._context(actions)

        outcome = AdStateMachine().run(context, self.spec)

        self.assertEqual(WorkflowStatus.SUCCESS, outcome.status)
        self.assertEqual([35], context.timing.clock.sleeps)
        self.assertEqual(1, len(actions.pressed))
        self.assertTrue(all(request is False for request in actions.screenshot_requests))

    def test_unchanged_ad_page_stops_at_configured_limits(self):
        actions = StubActions(self.start_target, self.exit_target, always_on_ad=True)
        context = self._context(actions)

        outcome = AdStateMachine().run(context, self.spec)

        self.assertEqual(WorkflowStatus.RETRYABLE_FAILURE, outcome.status)
        self.assertEqual(2, actions.observation_count)
        self.assertEqual(2, len(actions.pressed))
        self.assertEqual([35], context.timing.clock.sleeps)
        self.assertTrue(any(args[0] == "ad.recovery.required" for args, _ in context.events))

    def test_waits_one_round_then_closes_exit_prompt(self):
        prompt_target = target("退出提示", coordinate_locator("提示坐标", Point(0.5, 0.5)))
        prompt_close_target = target("退出弹窗关闭", coordinate_locator("关闭坐标", Point(0.8, 0.4)))
        actions = ExitPromptActions(
            self.start_target,
            prompt_target,
            prompt_close_target,
            self.exit_target,
        )
        context = self._context(actions)
        spec = AdSpec(
            start_markers=(self.start_target,),
            continue_targets=(),
            next_sequences=(),
            close_targets=(),
            final_close_targets=(),
            exit_targets=(self.exit_target,),
            exit_after_wait_with_back=True,
            exit_prompt_markers=(prompt_target,),
            exit_prompt_close_targets=(prompt_close_target,),
            completion_wait_seconds=35,
            entry_attempts=1,
            max_cycles=4,
            max_back_attempts=1,
        )

        outcome = AdStateMachine().run(context, spec)

        self.assertEqual(WorkflowStatus.SUCCESS, outcome.status)
        self.assertEqual([35], context.timing.clock.sleeps)
        self.assertEqual([SystemKey.BACK], actions.pressed)
        self.assertEqual([prompt_close_target.target_id], actions.clicked)
        event_types = [args[0] for args, _ in context.events]
        self.assertIn("ad.exit.requested", event_types)
        self.assertIn("ad.exit.prompt.closed", event_types)

    def test_reward_prompt_can_add_two_bounded_rounds(self):
        prompt_target = target("追加奖励提示", coordinate_locator("提示坐标", Point(0.5, 0.5)))
        prompt_continue_target = target("领取追加奖励", coordinate_locator("领取坐标", Point(0.5, 0.6)))
        prompt_close_target = target("退出弹窗关闭", coordinate_locator("关闭坐标", Point(0.8, 0.4)))
        actions = ExitPromptActions(
            self.start_target,
            prompt_target,
            prompt_close_target,
            self.exit_target,
            prompt_continue_target,
        )
        context = self._context(actions)
        spec = AdSpec(
            start_markers=(self.start_target,),
            continue_targets=(),
            next_sequences=(),
            close_targets=(),
            final_close_targets=(),
            exit_targets=(self.exit_target,),
            exit_after_wait_with_back=True,
            exit_prompt_markers=(prompt_target,),
            exit_prompt_continue_targets=(prompt_continue_target,),
            exit_prompt_close_targets=(prompt_close_target,),
            extra_rounds_min=0,
            extra_rounds_max=2,
            completion_wait_seconds=35,
            entry_attempts=1,
            max_cycles=8,
            max_back_attempts=1,
        )

        outcome = AdStateMachine().run(context, spec)

        self.assertEqual(WorkflowStatus.SUCCESS, outcome.status)
        self.assertEqual([35] * 3, context.timing.clock.sleeps)
        self.assertEqual([SystemKey.BACK] * 3, actions.pressed)
        self.assertEqual(
            [prompt_continue_target.target_id] * 2 + [prompt_close_target.target_id],
            actions.clicked,
        )
        self.assertEqual(3, outcome.outputs["wait_count"])

    def test_completion_signal_ends_fallback_wait_then_settles(self):
        completion_target = target(
            "奖励完成",
            coordinate_locator("完成坐标", Point(0.5, 0.2)),
        )
        prompt_target = target("退出提示", coordinate_locator("提示坐标", Point(0.5, 0.5)))
        prompt_close_target = target("退出关闭", coordinate_locator("关闭坐标", Point(0.8, 0.)))
        actions = CompletionExitPromptActions(
            self.start_target,
            prompt_target,
            prompt_close_target,
            self.exit_target,
            completion_target=completion_target,
            completion_after_checks=2,
        )
        context = self._context(actions)
        spec = AdSpec(
            start_markers=(self.start_target,),
            completion_markers=(completion_target,),
            continue_targets=(),
            next_sequences=(),
            close_targets=(),
            final_close_targets=(),
            exit_targets=(self.exit_target,),
            exit_after_wait_with_back=True,
            exit_prompt_markers=(prompt_target,),
            exit_prompt_close_targets=(prompt_close_target,),
            completion_wait_seconds=35,
            completion_check_interval_seconds_min=5,
            completion_check_interval_seconds_center=5,
            completion_check_interval_seconds_max=5,
            completion_settle_seconds_min=2,
            completion_settle_seconds_center=2,
            completion_settle_seconds_max=2,
            entry_attempts=1,
            max_cycles=4,
            max_back_attempts=1,
        )

        outcome = AdStateMachine().run(context, spec)

        self.assertEqual(WorkflowStatus.SUCCESS, outcome.status)
        self.assertEqual([5, 5, 2], context.timing.clock.sleeps)
        self.assertEqual(2, actions.completion_checks)
        event_types = [args[0] for args, _ in context.events]
        self.assertIn("ad.completion.detected", event_types)


if __name__ == "__main__":
    unittest.main()
