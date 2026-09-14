import unittest
from pathlib import Path
from types import SimpleNamespace

from hym.core.config import AppRunSettings, BehaviorSettings
from hym.core.events import InMemoryEventSink
from hym.core.models import ActivityInfo, AppIdentity, DeviceDescriptor, Observation, Point, WorkflowStatus
from hym.core.pages import PageMatchResult, PageMatchStatus
from hym.core.targets import ResolveResult, ResolveStatus, ResolvedTarget
from hym.runtime.behavior import BehaviorTiming
from hym.runtime.context import AppContext
from hym.testing import DeterministicRandom, FakeClock, InMemoryStateStore
from wechat_automation.config import ChatSettings, MomentsSettings, WalletSettings, WechatSettings
from wechat_automation.plugin import WechatPlugin


class StubSession:
    descriptor = DeviceDescriptor("device-1")


class StubDiagnostics:
    def capture(self, *args, **kwargs):
        return ()


class StubActions:
    def __init__(self):
        self.inputs = []
        self.taps = []
        self.observation = Observation(
            "device-1",
            ActivityInfo("com.tencent.mm", "com.tencent.mm.ui.LauncherUI"),
        )

    def observe_for(self, targets, *, include_screenshot):
        return self.observation

    def match_page(self, page, **kwargs):
        return PageMatchResult(page.page_id, PageMatchStatus.MATCHED, self.observation)

    def resolve_in(self, target, observation):
        return self._found(target.target_id, observation.observation_id)

    def tap_target(self, target, timeout=2.0):
        self.taps.append(target.target_id)
        return True

    def tap_first(self, targets, *, timeout=1.0):
        self.taps.append(targets[0].target_id)
        return targets[0].target_id

    def exists(self, target, timeout=1.0):
        return True

    def input_text(self, value):
        self.inputs.append(value)
        return True

    def press(self, key):
        return True

    def swipe_up(self):
        return True

    @staticmethod
    def _found(target_id, observation_id):
        return ResolveResult(
            ResolveStatus.FOUND,
            ResolvedTarget(target_id, "测试", Point(0.5, 0.5), 1.0, observation_id),
        )


def create_context():
    clock = FakeClock()
    random_source = DeterministicRandom()
    events = InMemoryEventSink()
    context = AppContext(
        app=AppIdentity("wechat", "com.tencent.mm", "微信"),
        settings=AppRunSettings("wechat"),
        session=StubSession(),
        timing=BehaviorTiming(BehaviorSettings(minimum_delay=0), clock, random_source),
        random_source=random_source,
        state=InMemoryStateStore(),
        events=events,
        diagnostics=StubDiagnostics(),
    )
    context.actions = StubActions()
    return context, events


class WechatPluginTest(unittest.TestCase):
    def test_home_recovery_checks_after_all_configured_back_presses(self):
        class RecoveryActions:
            def __init__(self):
                self.checks = 0
                self.presses = 0

            def match_page(self, page, **kwargs):
                self.checks += 1
                if self.checks == 4:
                    return PageMatchResult(page.page_id, PageMatchStatus.MATCHED)
                return PageMatchResult(page.page_id, PageMatchStatus.NOT_MATCHED)

            def press(self, key):
                self.presses += 1
                return True

        actions = RecoveryActions()
        context = SimpleNamespace(
            actions=actions,
            timing=SimpleNamespace(operation_delay=lambda: None),
        )
        plugin = WechatPlugin(WechatSettings(Path("automation.json"), root_attempts=3))

        self.assertTrue(plugin._go_home(context))
        self.assertEqual(3, actions.presses)
        self.assertEqual(4, actions.checks)

    def test_preview_opens_friend_without_typing_messages(self):
        settings = WechatSettings(
            Path("automation.json"),
            moments=MomentsSettings(enabled=False),
            wallet=WalletSettings(enabled=False),
            chat=ChatSettings(enabled=True, send=False, friend_name="测试好友"),
        )
        plugin = WechatPlugin(settings)
        context, events = create_context()

        outcome = plugin._chat(context)

        self.assertEqual(WorkflowStatus.SUCCESS, outcome.status)
        self.assertEqual(["测试好友"], context.actions.inputs)
        self.assertEqual("wechat.chat.previewed", events.events[-1].event_type)

    def test_real_send_is_limited_to_configured_two_messages_and_marked_daily(self):
        messages = ("第一条私密消息", "第二条私密消息")
        settings = WechatSettings(
            Path("automation.json"),
            moments=MomentsSettings(enabled=False),
            wallet=WalletSettings(enabled=False),
            chat=ChatSettings(
                enabled=True,
                send=True,
                friend_name="测试好友",
                message_groups=(messages,),
            ),
        )
        plugin = WechatPlugin(settings)
        context, events = create_context()

        outcome = plugin._chat(context)
        second_outcome = plugin._chat(context)

        self.assertEqual(WorkflowStatus.SUCCESS, outcome.status)
        self.assertEqual(WorkflowStatus.ALREADY_DONE, second_outcome.status)
        self.assertEqual(["测试好友", *messages], context.actions.inputs)
        serialized_events = repr([(event.message, event.data) for event in events.events])
        self.assertNotIn(messages[0], serialized_events)
        self.assertNotIn(messages[1], serialized_events)
        self.assertNotIn("测试好友", serialized_events)


if __name__ == "__main__":
    unittest.main()
