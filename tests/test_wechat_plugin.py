import unittest
from pathlib import Path
from types import SimpleNamespace

from hym.core.config import AppRunSettings, BehaviorSettings
from hym.core.events import InMemoryEventSink
from hym.core.models import ActivityInfo, AppIdentity, DeviceDescriptor, Observation, OcrText, Point, Rect, WorkflowStatus
from hym.core.pages import PageMatchResult, PageMatchStatus
from hym.core.targets import LocatorKind, ResolveResult, ResolveStatus, ResolvedTarget
from hym.runtime.behavior import BehaviorTiming
from hym.runtime.context import AppContext
from hym.testing import DeterministicRandom, FakeClock, InMemoryStateStore
from wechat_automation import targets
from wechat_automation.config import ChatSettings, MomentsSettings, WalletSettings, WechatSettings
from wechat_automation.plugin import WechatPlugin, _bill_transactions, _wallet_balance_minor


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

    def observe(self, **kwargs):
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
    def test_unavailable_wallet_page_is_reported_as_skipped_warning(self):
        context, events = create_context()
        context.ocr = SimpleNamespace(recognize=lambda screenshot: ())
        context.actions.observation = Observation(
            "device-1",
            ActivityInfo("com.tencent.mm", "com.tencent.mm.ui.LauncherUI"),
            screenshot=b"wallet",
        )
        plugin = WechatPlugin(WechatSettings(Path("automation.json")))

        outcome = plugin._capture_wallet(context)

        self.assertEqual(WorkflowStatus.SKIPPED, outcome.status)
        self.assertEqual("wechat.wallet.unavailable", events.events[-1].event_type)
        self.assertEqual("skipped", events.events[-1].status)

    def test_wallet_balance_remains_success_when_bill_is_unavailable(self):
        context, events = create_context()
        context.ocr = SimpleNamespace(
            recognize=lambda screenshot: (
                OcrText("钱包", Rect(0.4, 0.07, 0.6, 0.10), 1.0, "test"),
                OcrText("¥12.34", Rect(0.7, 0.14, 0.9, 0.17), 1.0, "test"),
            )
        )
        context.actions.observation = Observation(
            "device-1",
            ActivityInfo("com.tencent.mm", "com.tencent.mm.ui.LauncherUI"),
            screenshot=b"wallet",
        )
        original_tap_target = context.actions.tap_target
        context.actions.tap_target = lambda target, timeout=2.0: (
            False if target is targets.BILL_ENTRY else original_tap_target(target, timeout)
        )
        plugin = WechatPlugin(WechatSettings(Path("automation.json")))

        outcome = plugin._capture_wallet(context)

        self.assertEqual(WorkflowStatus.SUCCESS, outcome.status)
        self.assertEqual(1_234, outcome.outputs["balance_minor"])
        self.assertEqual("wechat.bill.unavailable", events.events[-1].event_type)

    def test_wallet_ocr_builds_balance_and_deduplicatable_bill_rows(self):
        texts = (
            OcrText("钱包", Rect(0.4, 0.07, 0.6, 0.10), 1.0, "test"),
            OcrText("¥476.47", Rect(0.7, 0.14, 0.9, 0.17), 1.0, "test"),
        )
        bill_texts = (
            OcrText("账单", Rect(0.4, 0.07, 0.6, 0.10), 1.0, "test"),
            OcrText("2022年12月", Rect(0.04, 0.21, 0.30, 0.24), 1.0, "test"),
            OcrText("商家转账-来自快手科技", Rect(0.2, 0.28, 0.7, 0.31), 1.0, "test"),
            OcrText("+0.30", Rect(0.84, 0.28, 0.96, 0.31), 1.0, "test"),
            OcrText("12月8日 13.23", Rect(0.2, 0.32, 0.5, 0.34), 1.0, "test"),
        )

        transactions, year = _bill_transactions(bill_texts, current_year=None, timezone=None)

        self.assertEqual(47_647, _wallet_balance_minor(texts))
        self.assertEqual(2022, year)
        self.assertEqual(1, len(transactions))
        self.assertEqual(30, transactions[0]["amount_minor"])
        self.assertEqual("income", transactions[0]["direction"])
        self.assertEqual(64, len(str(transactions[0]["fingerprint"])))

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

    def test_home_page_requires_bottom_navigation_not_only_launcher_activity(self):
        self.assertEqual((r"LauncherUI$",), targets.HOME_PAGE.activity_patterns)
        self.assertTrue(
            all(locator.kind is not LocatorKind.ACTIVITY for locator in targets.HOME_MARKER.locators)
        )

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
