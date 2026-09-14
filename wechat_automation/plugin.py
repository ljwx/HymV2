from __future__ import annotations

from dataclasses import dataclass

from hym.core.models import AppIdentity, SystemKey, WorkflowResult, WorkflowStatus
from hym.core.pages import ObservationProfile
from hym.core.randomness import bounded_normal_int
from hym.runtime.context import AppContext
from hym.runtime.workflow import StepDefinition, StepOutcome, WorkflowDefinition, WorkflowExecutor
from wechat_automation.config import WechatSettings
from wechat_automation import targets


@dataclass(frozen=True, slots=True)
class WechatSpec:
    identity: AppIdentity = AppIdentity("wechat", targets.WECHAT_PACKAGE, "微信")
    display_name: str = "微信"
    observation_profile: ObservationProfile = ObservationProfile()


class WechatPlugin:
    """微信独立流程，只复用设备、定位、日志和诊断基础设施。"""

    def __init__(self, settings: WechatSettings) -> None:
        self.settings = settings
        self.spec = WechatSpec()

    @property
    def app_id(self) -> str:
        return self.spec.identity.app_id

    def run(self, context: AppContext) -> WorkflowResult:
        definition = self.build_workflow(context)
        return WorkflowExecutor().run(
            context,
            definition.workflow_id,
            definition.display_name,
            definition.steps,
        )

    def build_workflow(self, context: AppContext) -> WorkflowDefinition:
        steps = [
            StepDefinition(
                "启动微信",
                "启动微信",
                self._start_app,
                required=True,
                max_attempts=2,
                continue_on_failure=False,
                recovery=self._restart_app,
                allow_interruption_after=False,
            )
        ]
        view_steps: list[StepDefinition] = []
        if self.settings.moments.enabled:
            view_steps.append(
                StepDefinition("查看朋友圈", "查看朋友圈", self._browse_moments, recovery=self._recover_home)
            )
        if self.settings.wallet.enabled:
            view_steps.append(
                StepDefinition("查看零钱", "查看零钱", self._capture_wallet, recovery=self._recover_home)
            )
        if self.settings.randomize_view_order and len(view_steps) > 1 and context.random.random() < 0.5:
            view_steps.reverse()
        steps.extend(view_steps)
        if self.settings.chat.enabled:
            # 聊天固定放在最后，失败时不会影响查看类任务。
            steps.append(
                StepDefinition("指定好友聊天", "指定好友聊天", self._chat, recovery=self._recover_home)
            )
        return WorkflowDefinition("wechat_activity", "微信基本操作", tuple(steps))

    def _start_app(self, context: AppContext) -> StepOutcome:
        result = context.session.start_app(self.spec.identity)
        if not result.succeeded:
            return StepOutcome.failure(f"启动微信失败: {result.message}")
        context.timing.wait(self.settings.launch_wait_seconds)
        return StepOutcome.success("微信启动完成")

    def _restart_app(self, context: AppContext) -> None:
        context.session.stop_app(self.spec.identity)
        context.timing.operation_delay()

    def _recover_home(self, context: AppContext) -> None:
        self._go_home(context)

    def _go_home(self, context: AppContext) -> bool:
        for attempt in range(self.settings.root_attempts + 1):
            if context.actions.match_page(targets.HOME_PAGE, visual_fallback=False).matched:
                return True
            if attempt >= self.settings.root_attempts:
                break
            context.actions.press(SystemKey.BACK)
            context.timing.operation_delay()
        return False

    def _browse_moments(self, context: AppContext) -> StepOutcome:
        if not self._go_home(context):
            return StepOutcome.failure("无法返回微信首页")
        if not context.actions.tap_target(targets.DISCOVER_TAB, timeout=1.5):
            return StepOutcome.failure("没有找到发现标签")
        context.timing.operation_delay()
        if not context.actions.tap_target(targets.MOMENTS_ENTRY, timeout=2.0):
            return StepOutcome.failure("没有找到朋友圈入口")
        context.timing.wait(self.settings.page_wait_seconds)
        if not context.actions.match_page(targets.MOMENTS_PAGE_SPEC).matched:
            return StepOutcome.failure("进入后没有识别到朋友圈页面")

        count = bounded_normal_int(
            context.random,
            self.settings.moments.swipes_min,
            self.settings.moments.swipes_max,
            center=self.settings.moments.swipes_center,
            stddev=self.settings.moments.swipes_stddev,
        )
        for _ in range(count):
            self._wait_range(
                context,
                self.settings.moments.pause_min_seconds,
                self.settings.moments.pause_max_seconds,
                self.settings.moments.pause_center_seconds,
                self.settings.moments.pause_stddev_seconds,
            )
            if not context.actions.swipe_up():
                return StepOutcome.failure("朋友圈浏览时滑动失败")
        self._wait_range(
            context,
            self.settings.moments.pause_min_seconds,
            self.settings.moments.pause_max_seconds,
            self.settings.moments.pause_center_seconds,
            self.settings.moments.pause_stddev_seconds,
        )
        context.actions.press(SystemKey.BACK)
        return StepOutcome.success("朋友圈浏览完成", swipe_count=count)

    def _capture_wallet(self, context: AppContext) -> StepOutcome:
        if self.settings.wallet.capture_once_per_day and context.daily_value("wallet_capture") is not None:
            return StepOutcome(WorkflowStatus.ALREADY_DONE, "今天已经记录过零钱页面")
        if not self._go_home(context):
            return StepOutcome.failure("查看零钱时无法返回微信首页")
        if not context.actions.tap_target(targets.ME_TAB, timeout=1.5):
            return StepOutcome.failure("没有找到我的标签")
        context.timing.operation_delay()
        if context.actions.tap_first(targets.SERVICE_ENTRIES, timeout=2.0) is None:
            return StepOutcome.failure("没有找到服务或支付入口")
        context.timing.wait(self.settings.page_wait_seconds)
        if not context.actions.tap_target(targets.WALLET_ENTRY, timeout=2.0):
            return StepOutcome.failure("没有找到钱包入口")
        context.timing.wait(self.settings.page_wait_seconds)
        if not context.actions.tap_target(targets.BALANCE_ENTRY, timeout=2.0):
            return StepOutcome.failure("没有找到零钱入口")
        context.timing.wait(self.settings.page_wait_seconds)

        page_result = context.actions.match_page(targets.BALANCE_PAGE_SPEC)
        observation = page_result.observation
        if not page_result.matched or observation is None:
            return StepOutcome.failure("进入后没有识别到零钱页面")
        artifacts = context.diagnostics.capture(
            "wechat-wallet",
            observation,
            metadata={
                "schema_version": "1.0",
                "purpose": "微信零钱页面记录",
                "trace_id": context.trace_id,
                "device_id": context.device_id,
            },
        )
        if not artifacts:
            return StepOutcome.failure("零钱页面已打开，但截图和页面结构保存失败")
        context.mark_daily("wallet_capture", {"artifacts": [item.uri for item in artifacts]})
        context.emit(
            "wechat.wallet.captured",
            "零钱页面记录",
            "微信零钱页面已保存到本地诊断目录",
            workflow_id="wechat_activity",
            step_id="查看零钱",
            status="success",
            data={"artifact_count": len(artifacts)},
            artifacts=artifacts,
        )
        context.actions.press(SystemKey.BACK)
        return StepOutcome(
            WorkflowStatus.SUCCESS,
            "零钱页面记录完成",
            {"artifact_count": len(artifacts)},
            artifacts,
        )

    def _chat(self, context: AppContext) -> StepOutcome:
        chat = self.settings.chat
        friend_name = chat.friend_name.strip()
        if chat.once_per_day and context.daily_value("chat_sent") is not None:
            return StepOutcome(WorkflowStatus.ALREADY_DONE, "今天已经执行过指定好友聊天")
        if not self._go_home(context):
            return StepOutcome.failure("聊天前无法返回微信首页")
        if not context.actions.tap_target(targets.CHAT_TAB, timeout=1.5):
            return StepOutcome.failure("没有找到微信聊天标签")
        context.timing.operation_delay()
        if not context.actions.tap_target(targets.SEARCH_ENTRY, timeout=2.0):
            return StepOutcome.failure("没有找到微信搜索入口")
        context.timing.operation_delay()
        if not context.actions.tap_target(targets.SEARCH_INPUT, timeout=1.5):
            return StepOutcome.failure("没有找到微信搜索输入框")
        if not context.actions.input_text(friend_name):
            return StepOutcome.failure("好友名称输入失败")
        context.timing.wait(self.settings.page_wait_seconds)
        if not context.actions.tap_target(targets.friend_result(friend_name), timeout=2.0):
            return StepOutcome.failure("没有找到配置的指定好友")
        context.timing.wait(self.settings.page_wait_seconds)
        if not context.actions.exists(targets.conversation_title(friend_name), timeout=1.5):
            return StepOutcome.failure("聊天页标题与指定好友不一致，已停止发送")

        if not chat.send:
            context.emit(
                "wechat.chat.previewed",
                "聊天预览完成",
                "已进入指定好友聊天页，预览模式没有发送消息",
                workflow_id="wechat_activity",
                step_id="指定好友聊天",
                status="success",
            )
            return StepOutcome.success("已进入指定好友聊天页，预览模式未发送消息", sent_count=0)

        messages = context.random.choice(chat.message_groups)
        sent_count = 0
        for index, message in enumerate(messages, start=1):
            if not context.actions.tap_target(targets.MESSAGE_INPUT, timeout=1.5):
                return self._chat_failure(context, sent_count, "没有找到消息输入框")
            if not context.actions.input_text(message):
                return self._chat_failure(context, sent_count, "消息文本输入失败")
            if not context.actions.tap_target(targets.SEND_BUTTON, timeout=1.5):
                return self._chat_failure(context, sent_count, "没有找到发送按钮")
            sent_count += 1
            context.mark_daily("chat_sent", {"sent_count": sent_count})
            context.emit(
                "wechat.chat.message_sent",
                "聊天消息已发送",
                f"指定好友的第 {index} 条消息已发送",
                workflow_id="wechat_activity",
                step_id="指定好友聊天",
                status="success",
                data={"message_index": index, "text_length": len(message)},
            )
            if index < len(messages):
                self._wait_range(
                    context,
                    chat.interval_min_seconds,
                    chat.interval_max_seconds,
                    chat.interval_center_seconds,
                    chat.interval_stddev_seconds,
                )
        return StepOutcome.success("指定好友聊天完成", sent_count=sent_count)

    def _chat_failure(self, context: AppContext, sent_count: int, message: str) -> StepOutcome:
        if sent_count:
            return StepOutcome(
                WorkflowStatus.RETRYABLE_FAILURE,
                f"{message}，已发送 {sent_count} 条；今天不再自动补发",
                {"sent_count": sent_count},
            )
        return StepOutcome.failure(message)

    @staticmethod
    def _wait_range(
        context: AppContext,
        minimum: float,
        maximum: float,
        center: float,
        stddev: float,
    ) -> None:
        context.timing.clock.sleep(
            context.timing.range_seconds(
                minimum,
                maximum,
                center=center,
                stddev=stddev,
            )
        )
