from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import re

from hym.core.control import TaskScope
from hym.core.models import AppIdentity, OcrText, SystemKey, WorkflowResult, WorkflowStatus
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
        capabilities = []
        if settings.moments.enabled or settings.chat.enabled:
            capabilities.append("content")
        if settings.wallet.enabled:
            capabilities.append("balance")
        spec = WechatSpec()
        self.spec = replace(
            spec,
            identity=replace(
                spec.identity,
                metadata={**spec.identity.metadata, "capabilities": tuple(capabilities)},
            ),
        )

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
                task_scope=TaskScope.SETUP,
            )
        ]
        view_steps: list[StepDefinition] = []
        if self.settings.moments.enabled:
            view_steps.append(
                StepDefinition(
                    "查看朋友圈",
                    "查看朋友圈",
                    self._browse_moments,
                    recovery=self._recover_home,
                    task_scope=TaskScope.MAIN,
                )
            )
        if self.settings.wallet.enabled:
            view_steps.append(
                StepDefinition(
                    "查看零钱",
                    "查看零钱",
                    self._capture_wallet,
                    recovery=self._recover_home,
                    task_scope=TaskScope.BALANCE,
                )
            )
        if self.settings.randomize_view_order and len(view_steps) > 1 and context.random.random() < 0.5:
            view_steps.reverse()
        steps.extend(view_steps)
        if self.settings.chat.enabled:
            # 聊天固定放在最后，失败时不会影响查看类任务。
            steps.append(
                StepDefinition(
                    "指定好友聊天",
                    "指定好友聊天",
                    self._chat,
                    recovery=self._recover_home,
                    task_scope=TaskScope.MAIN,
                )
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
        recorded = context.daily_value("wallet_capture")
        if self.settings.wallet.capture_once_per_day and _has_wallet_snapshot(recorded):
            return StepOutcome(WorkflowStatus.ALREADY_DONE, "今天已经记录过微信零钱和账单")
        if context.ocr is None:
            return StepOutcome.failure("微信资产采集需要启用 OCR")
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

        observation = context.actions.observe(include_ui_tree=False, include_screenshot=True)
        if observation is None or observation.screenshot is None:
            return StepOutcome.failure("微信钱包页面截图失败")
        wallet_texts = context.ocr.recognize(observation.screenshot)
        if not any(item.text.strip() == "钱包" for item in wallet_texts):
            return StepOutcome.failure("进入后没有识别到微信钱包页面")
        balance_minor = _wallet_balance_minor(wallet_texts)
        if balance_minor is None:
            return StepOutcome.failure("没有识别到微信零钱总额")

        balance = {
            "asset_key": "cash",
            "asset_label": "零钱",
            "amount_minor": balance_minor,
            "scale": 2,
            "unit": "元",
        }
        wallet_data = {
            "business_date": context.business_date.isoformat(),
            "balances": [balance],
        }
        context.emit(
            "wechat.wallet.snapshot",
            "微信零钱记录",
            "微信零钱总额已记录",
            workflow_id="wechat_activity",
            step_id="查看零钱",
            status="success",
            data=wallet_data,
        )

        if not context.actions.tap_target(targets.BILL_ENTRY, timeout=2.0):
            return StepOutcome.failure("没有找到微信账单入口")
        context.timing.wait(self.settings.page_wait_seconds)
        transactions = self._read_transactions(context)
        if not transactions:
            return StepOutcome.failure("没有识别到微信账单交易")
        bill_data = {
            "business_date": context.business_date.isoformat(),
            "transactions": transactions,
        }
        context.emit(
            "wechat.bill.snapshot",
            "微信账单记录",
            f"微信最近账单已记录 {len(transactions)} 笔",
            workflow_id="wechat_activity",
            step_id="查看零钱",
            status="success",
            data=bill_data,
        )
        context.mark_daily(
            "wallet_capture",
            {
                **wallet_data,
                "transaction_count": len(transactions),
            },
        )
        context.actions.press(SystemKey.BACK)
        context.actions.press(SystemKey.BACK)
        return StepOutcome.success(
            "微信零钱和账单记录完成",
            balance_minor=balance_minor,
            transaction_count=len(transactions),
        )

    def _read_transactions(self, context: AppContext) -> list[dict[str, object]]:
        assert context.ocr is not None
        settings = self.settings.wallet
        found: dict[str, dict[str, object]] = {}
        current_year: int | None = None
        for page in range(settings.max_bill_pages):
            observation = context.actions.observe(include_ui_tree=False, include_screenshot=True)
            if observation is None or observation.screenshot is None:
                break
            texts = context.ocr.recognize(observation.screenshot)
            if page == 0 and not any(item.text.strip() == "账单" for item in texts):
                return []
            page_items, current_year = _bill_transactions(
                texts,
                current_year=current_year,
                timezone=context.timing.clock.now().astimezone().tzinfo,
            )
            for item in page_items:
                found.setdefault(str(item["fingerprint"]), item)
                if len(found) >= settings.transaction_limit:
                    return list(found.values())[: settings.transaction_limit]
            if page + 1 >= settings.max_bill_pages or not context.actions.swipe_up():
                break
            context.timing.wait(self.settings.page_wait_seconds)
        return list(found.values())[: settings.transaction_limit]

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


_AMOUNT_RE = re.compile(r"^([+-])\s*[¥￥]?\s*(\d[\d,]*(?:\.\d{1,2})?)$")
_DATE_RE = re.compile(r"(\d{1,2})月(\d{1,2})日\s*(\d{1,2})[:.](\d{2})")
_MONTH_RE = re.compile(r"(\d{4})年\s*(\d{1,2})月")


def _has_wallet_snapshot(recorded: object) -> bool:
    if not isinstance(recorded, dict):
        return False
    value = recorded.get("value")
    return isinstance(value, dict) and bool(value.get("balances")) and int(value.get("transaction_count", 0)) > 0


def _wallet_balance_minor(texts: tuple[OcrText, ...]) -> int | None:
    for item in sorted(texts, key=lambda value: value.bounds.top):
        if item.bounds.top > 0.30:
            continue
        match = re.search(r"[¥￥]\s*(\d[\d,]*(?:\.\d{1,2})?)", item.text)
        if match is not None:
            return _decimal_minor(match.group(1), 2)
    return None


def _bill_transactions(
    texts: tuple[OcrText, ...],
    *,
    current_year: int | None,
    timezone,
) -> tuple[list[dict[str, object]], int | None]:
    ordered = sorted(texts, key=lambda item: (item.bounds.top, item.bounds.left))
    headers = [
        (item.bounds.top, int(match.group(1)))
        for item in ordered
        if (match := _MONTH_RE.search(item.text.replace(" ", ""))) is not None
    ]
    transactions: list[dict[str, object]] = []
    for amount_item in ordered:
        compact_amount = amount_item.text.replace(" ", "")
        amount_match = _AMOUNT_RE.fullmatch(compact_amount)
        if amount_match is None or amount_item.bounds.left < 0.70 or amount_item.bounds.top < 0.24:
            continue
        year = current_year
        for header_top, header_year in headers:
            if header_top <= amount_item.bounds.top:
                year = header_year
            else:
                break
        if year is None:
            continue
        title = next(
            (
                item.text.strip()
                for item in ordered
                if item.bounds.left < 0.72
                and abs(item.bounds.top - amount_item.bounds.top) <= 0.025
                and item is not amount_item
                and not _MONTH_RE.search(item.text)
            ),
            "",
        )
        date_item = next(
            (
                item
                for item in ordered
                if amount_item.bounds.top + 0.015 <= item.bounds.top <= amount_item.bounds.top + 0.075
                and _DATE_RE.search(item.text.replace(" ", "")) is not None
            ),
            None,
        )
        if not title or date_item is None:
            continue
        date_match = _DATE_RE.search(date_item.text.replace(" ", ""))
        assert date_match is not None
        month, day, hour, minute = map(int, date_match.groups())
        try:
            occurred = datetime(year, month, day, hour, minute, tzinfo=timezone)
        except ValueError:
            continue
        amount_minor = _decimal_minor(amount_match.group(2), 2)
        if amount_minor is None:
            continue
        direction = "income" if amount_match.group(1) == "+" else "expense"
        occurred_text = f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}"
        fingerprint_source = "|".join(
            (title, occurred_text, direction, str(amount_minor), "CNY")
        )
        transactions.append(
            {
                "fingerprint": hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest(),
                "title": title,
                "occurred_at_text": occurred_text,
                "occurred_at_ms": round(occurred.timestamp() * 1000),
                "amount_minor": amount_minor,
                "scale": 2,
                "currency": "CNY",
                "direction": direction,
            }
        )
    latest_year = headers[-1][1] if headers else current_year
    return transactions, latest_year


def _decimal_minor(value: str, scale: int) -> int | None:
    try:
        number = Decimal(value.replace(",", ""))
        return int((number * (Decimal(10) ** scale)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except InvalidOperation:
        return None
