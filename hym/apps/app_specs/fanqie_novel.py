"""
番茄免费小说业务核对说明

每日流程：启动 -> 签到/阅读随机先后 -> 按概率看广告 -> 记录余额和提现门槛。

任务与限制：
- 主线选择小说阅读，不用短视频替代；进入书籍后横向翻页，页数和停留时间均由配置控制。
- 签到每天只提交一次，只有看到完成文案或“奖励加倍惊喜”结果层才记为成功。
- 广告失败只结束当前广告任务，不阻断阅读和余额记录。

页面与状态标记：
- 首页底栏“书城”，书籍卡片 ID 为 gb1；阅读页优先识别 ReaderActivity，再用文字兜底。
- 任务入口为底栏“赚钱”，任务页包含“福利中心/签到领金币”。
- 签到结果可能由画布渲染“奖励加倍惊喜/N金币打包带走”，需用 OCR 确认并主动领取翻倍视频奖励。
- 广告只匹配“看视频赚金币”；通用“立即领取”可能是新人礼，不能当广告入口。
- 同一状态出现新 ID 或文案时，在原 target 内追加 locator，不要改 target_id。
"""

from __future__ import annotations

from dataclasses import dataclass

from hym.apps.app_specs.common import TaskPagePopupNavigator, text_target
from hym.apps.plugin import ComposedAppPlugin, create_daily_plugin
from hym.apps.specs import (
    AdSpec,
    AppSpec,
    BalanceAssetSpec,
    BalanceSpec,
    CheckInSpec,
    CheckInStageSpec,
    NavigationSpec,
    NewsContentSpec,
    PopupDismissSpec,
    WithdrawalSpec,
)
from hym.apps.targets import (
    activity_locator,
    coordinate_locator,
    id_locator,
    ocr_locator,
    query_locator,
    regex_locator,
    target,
    text_locator,
)
from hym.core.models import AppIdentity, Point, Rect, SwipeGesture, SystemKey, UiTreeSource
from hym.core.pages import ObservationProfile, PageSpec
from hym.runtime.context import AppContext
from hym.runtime.navigation import NavigationController
from hym.runtime.workflow import StepOutcome


def fanqie_novel_spec() -> AppSpec:
    package_name = "com.dragon.read"
    prefix = f"{package_name}:id/"
    profile = ObservationProfile(UiTreeSource.APPLICATION)

    home_tab = target(
        "番茄小说书城标签",
        id_locator("书城底栏ID", prefix + "aro"),
        text_locator("书城底栏文本", "书城", region=Rect(0.0, 0.90, 0.25, 1.0)),
        required=True,
    )
    book_item = target(
        "番茄小说书籍卡片",
        query_locator(
            "书籍卡片ID",
            priority=10,
            options={"resource_id": prefix + "gb1", "clickable": True, "pick": "random"},
        ),
        required=True,
    )
    task_entry = target(
        "番茄小说赚钱入口",
        id_locator("赚钱底栏ID", prefix + "arw"),
        text_locator("赚钱底栏文本", "赚钱", region=Rect(0.35, 0.90, 0.65, 1.0)),
        required=True,
    )
    task_marker = target(
        "番茄小说任务页标记",
        text_locator("福利中心文本", "福利中心"),
        text_locator("签到领金币文本", "签到领金币", priority=21),
        ocr_locator("福利中心OCR", "福利中心", confidence=0.45),
        required=True,
    )
    reader_marker = target(
        "番茄小说阅读页标记",
        activity_locator(
            "阅读Activity",
            r"(?:^|\.)reader\.ui\.ReaderActivity$",
            package_name=package_name,
            priority=5,
        ),
        text_locator("评论入口文本", "开启评论"),
        regex_locator("阅读页码", r"[1-9]\d*/[1-9]\d*", priority=21),
        required=True,
    )
    ad_close = target(
        "番茄小说广告关闭",
        text_locator("广告关闭文本", "关闭"),
        coordinate_locator("广告右上角关闭坐标", Point(0.94, 0.06)),
    )
    check_in_ad_entry = target(
        "番茄小说签到翻倍视频",
        ocr_locator(
            "签到翻倍视频OCR",
            r"看视频(?:签到|领)?\s*\+?\d+\s*金币",
            mode="regex",
            region=Rect(0.18, 0.55, 0.82, 0.72),
            confidence=0.3,
        ),
    )
    ad = AdSpec(
        start_markers=(
            target(
                "番茄小说广告倒计时",
                text_locator("广告倒计时文本", "秒后可领奖励", contains=True),
                ocr_locator(
                    "广告倒计时OCR",
                    r"\d+秒后可领奖励",
                    mode="regex",
                    region=Rect(0.55, 0.02, 0.98, 0.14),
                    confidence=0.4,
                ),
            ),
            text_target("番茄小说广告页面", "广告", contains=True),
        ),
        completion_markers=(
            target(
                "番茄小说广告奖励到账",
                text_locator("广告领取成功文本", "领取成功", contains=True),
                ocr_locator(
                    "广告领取成功OCR",
                    "领取成功",
                    region=Rect(0.62, 0.02, 0.98, 0.14),
                    confidence=0.4,
                ),
            ),
            text_target("番茄小说广告奖励获得", "已获得", contains=True),
        ),
        continue_targets=(),
        next_sequences=(),
        close_targets=(ad_close,),
        final_close_targets=(ad_close,),
        exit_targets=(task_marker, home_tab),
        exit_after_wait_with_back=True,
        completion_wait_seconds=50.0,
    )

    return AppSpec(
        identity=AppIdentity("fanqie_novel", package_name, "番茄免费小说", "1.0.0"),
        display_name="番茄免费小说",
        navigation=NavigationSpec(
            home_marker=book_item,
            home_tab=home_tab,
            task_entry=task_entry,
            task_marker=task_marker,
            reselect_home_tab=False,
            home_page=PageSpec(
                "fanqie_novel.home",
                package_name,
                (home_tab, book_item),
                minimum_markers=2,
                observation_profile=profile,
            ),
            task_page=PageSpec(
                "fanqie_novel.task",
                package_name,
                (task_marker,),
                observation_profile=profile,
            ),
        ),
        check_in=CheckInSpec(
            stages=(
                CheckInStageSpec(
                    "领取每日签到",
                    (
                        target(
                            "番茄小说签到按钮",
                            text_locator("去签到文本", "去签到"),
                            text_locator("立即签到文本", "立即签到", priority=21),
                            ocr_locator("去签到OCR", "去签到", confidence=0.45),
                        ),
                    ),
                ),
            ),
            success_targets=(
                target(
                    "番茄小说签到成功",
                    text_locator("现金红包到账文本", "送你现金红包", contains=True),
                    text_locator("已签到文本", "已签到", contains=True),
                    text_locator("明日再来文本", "明日再来", priority=21),
                    regex_locator("今日签到金币", r"今日签到领\d+金币", priority=22),
                    regex_locator("连续签到天数", r"已连续签到[1-9]\d*天", priority=23),
                    ocr_locator(
                        "签到奖励加倍OCR",
                        r"(?:今日签到领\d+金币|奖励加倍惊喜|\d+金币打包带走)",
                        mode="regex",
                        region=Rect(0.08, 0.12, 0.88, 0.38),
                        confidence=0.4,
                        priority=24,
                    ),
                    required=True,
                ),
            ),
            post_ad_target=check_in_ad_entry,
            close_target=target(
                "番茄小说签到结果关闭",
                coordinate_locator("签到结果底部关闭坐标", Point(0.50, 0.73)),
            ),
        ),
        balance=BalanceSpec(
            assets=(
                BalanceAssetSpec(
                    "coin",
                    "金币",
                    target(
                        "番茄小说金币余额",
                        ocr_locator(
                            "金币余额OCR",
                            r"\d+(?:\.\d+)?",
                            mode="regex",
                            region=Rect(0.04, 0.07, 0.35, 0.25),
                            confidence=0.4,
                        ),
                    ),
                    unit="金币",
                ),
                BalanceAssetSpec(
                    "cash",
                    "现金",
                    target(
                        "番茄小说现金余额",
                        ocr_locator(
                            "现金余额OCR",
                            r"\d+(?:\.\d+)?",
                            mode="regex",
                            region=Rect(0.30, 0.07, 0.70, 0.25),
                            confidence=0.4,
                        ),
                        ocr_locator(
                            "现金为零提示OCR",
                            "0点自动兑现金",
                            region=Rect(0.05, 0.15, 0.70, 0.28),
                            confidence=0.4,
                            priority=81,
                        ),
                    ),
                    scale=2,
                    unit="元",
                ),
            ),
        ),
        withdrawal=WithdrawalSpec(
            entry_sequence=(
                target(
                    "番茄小说提现入口",
                    text_locator("现金收益文本", "现金收益", contains=True),
                    coordinate_locator("顶部现金区域坐标", Point(0.48, 0.17)),
                ),
            ),
            available_region=Rect(0.05, 0.12, 0.55, 0.28),
            minimum_region=Rect(0.05, 0.30, 0.95, 0.47),
            details_region=Rect(0.03, 0.28, 0.97, 0.88),
        ),
        ad=ad,
        ad_entry=target(
            "番茄小说广告奖励入口",
            text_locator("看视频赚金币文本", "看视频赚金币", contains=True),
        ),
        duration_reward=None,
        # 规格声明为文字内容，实际翻页由本 App 的专用任务完成。
        content=NewsContentSpec(book_item, reader_marker),
        observation_profile=profile,
        metadata={"content_mode": "novel"},
    )


@dataclass(frozen=True, slots=True)
class FanqieNovelContentTask:
    """番茄阅读器使用横向翻页，不能复用新闻纵向滚动。"""

    spec: AppSpec
    navigation: NavigationController

    def run(self, context: AppContext) -> StepOutcome:
        content = self.spec.news
        if content is None:
            return StepOutcome.failure("番茄小说缺少阅读规格")
        progress = context.step_progress("浏览内容")
        resumed_reader = bool(progress) and context.actions.exists(
            content.detail_marker,
            timeout=2.0,
        )
        if not resumed_reader and not self.navigation.go_home(context, select_tab=True):
            return StepOutcome.failure("无法进入番茄小说书城")
        if not resumed_reader:
            if not context.actions.tap_target(content.feed_item, timeout=2.0):
                return StepOutcome.failure("没有找到可阅读的书籍")
            context.timing.operation_delay()
            start_reading = text_target("番茄小说开始阅读提示", "左滑开始阅读", contains=True)
            if context.actions.exists(start_reading, timeout=1.5):
                self._turn_page(context)
                context.timing.operation_delay()
            if not context.actions.exists(content.detail_marker, timeout=3.0):
                return StepOutcome.failure("进入书籍后没有识别到阅读页")

        if "target_pages" not in progress:
            progress.update(
                {
                    "content_kind": "novel",
                    "target_pages": context.sample_count("novel_page_count", 4, 7),
                    "next_page": 1,
                }
            )
        pages = int(progress["target_pages"])
        for index in range(int(progress.get("next_page", 1)), pages + 1):
            context.timing.clock.sleep(
                context.sample_seconds("novel_page_seconds", 8.0, 14.0, default_center=10.0)
            )
            if index < pages:
                self._turn_page(context)
            progress["next_page"] = index + 1
            context.reach_safe_point("content.novel.page", page_index=index, target_pages=pages)
        context.actions.press(SystemKey.BACK)
        context.clear_step_progress("浏览内容")
        return StepOutcome.success("小说阅读完成", pages=pages)

    @staticmethod
    def _turn_page(context: AppContext) -> None:
        context.session.swipe(
            SwipeGesture(Point(0.82, 0.56), Point(0.18, 0.56), context.timing.swipe_duration())
        )


def create_plugin() -> ComposedAppPlugin:
    spec = fanqie_novel_spec()
    navigation = NavigationController(spec)
    welcome_popup = PopupDismissSpec(
        marker=text_target("番茄小说任务欢迎弹窗", "看视频领", contains=True),
        close_target=target(
            "番茄小说任务欢迎弹窗关闭",
            coordinate_locator("欢迎弹窗底部关闭坐标", Point(0.50, 0.75)),
        ),
    )
    jump_game_popup = PopupDismissSpec(
        marker=target(
            "番茄小说跳一跳活动弹窗",
            ocr_locator(
                "跳一跳活动OCR",
                r"(?:玩跳一跳|跳一跳赢大额金币)",
                mode="regex",
                region=Rect(0.15, 0.14, 0.85, 0.36),
                confidence=0.4,
            ),
        ),
        close_target=target(
            "番茄小说跳一跳活弹窗关闭",
            coordinate_locator("跳一跳底部关闭坐标", Point(0.50, 0.80)),
        ),
    )
    reservation_popup = PopupDismissSpec(
        marker=text_target("番茄小说预约礼包弹窗", "预约最高领", contains=True),
        close_target=target(
            "番茄小说预约礼包弹窗关闭",
            coordinate_locator("预约礼包底部关闭坐标", Point(0.50, 0.74)),
        ),
    )
    return create_daily_plugin(
        spec,
        navigation=navigation,
        task_page_navigator=TaskPagePopupNavigator(
            navigation,
            (welcome_popup, jump_game_popup, reservation_popup),
            max_dismissals=5,
            check_after_entry=True,
        ),
        content_handler=FanqieNovelContentTask(spec, navigation).run,
    )
