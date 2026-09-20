"""
今日头条极速版业务核对说明

每日流程：启动 -> 浏览新闻 -> 按概率执行小说/广告奖励 -> 记录余额和提现门槛。

任务与限制：
- 当前版本没有找到稳定、独立的头条签到入口，不把合作方签到误记为本 App 签到。
- 主线选择文章，文章和视频共用时长奖励，但文章入口与详情页标记更稳定。
- 小说 30 秒奖励、已达标时长红包和广告属于附加任务，入口缺失时跳过，不影响主线。

页面与状态标记：
- 首页文章卡片 ID 为 adk，详情页包含“友善评论”；底栏入口为“任务”。
- 任务页使用“看文章或视频/现金收益”识别；已出现的“待领取”红包会在本页限量领取。
- 新页面只在本文件增加分支或 locator，保留已有 target_id 以便追踪日志。
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
    DurationRewardSpec,
    NavigationSpec,
    NewsContentSpec,
    PopupDismissSpec,
    WithdrawalSpec,
)
from hym.apps.targets import (
    activity_locator,
    coordinate_locator,
    desc_locator,
    id_locator,
    ocr_locator,
    query_locator,
    target,
    text_locator,
)
from hym.core.control import TaskScope
from hym.core.events import EventLevel
from hym.core.models import AppIdentity, Point, Rect, SystemKey, UiTreeSource
from hym.core.pages import ObservationProfile, PageSpec
from hym.runtime.context import AppContext
from hym.runtime.navigation import NavigationController
from hym.runtime.workflow import StepDefinition, StepOutcome


def toutiao_lite_spec() -> AppSpec:
    package_name = "com.ss.android.article.lite"
    prefix = f"{package_name}:id/"
    # 系统无障碍树会与 Poco 的 UiAutomation 会话冲突，本 App 只在页面确认时按需 OCR。
    profile = ObservationProfile(UiTreeSource.APPLICATION)

    home_tab = target(
        "头条极速版首页标签",
        text_locator("首页底栏文本", "首页", region=Rect(0.0, 0.88, 0.24, 1.0)),
        ocr_locator(
            "首页底栏OCR",
            "首页",
            mode="exact",
            region=Rect(0.0, 0.88, 0.24, 1.0),
            confidence=0.45,
        ),
        coordinate_locator("首页底栏坐标", Point(0.10, 0.97)),
        required=True,
    )
    home_marker = target(
        "头条极速版首页标记",
        activity_locator(
            "头条主Activity",
            r"SplashActivity$",
            package_name=package_name,
        ),
        text_locator("推荐顶部文本", "推荐", region=Rect(0.05, 0.08, 0.35, 0.24)),
        ocr_locator(
            "推荐顶部OCR",
            "推荐",
            mode="exact",
            region=Rect(0.05, 0.08, 0.35, 0.24),
            confidence=0.45,
        ),
        required=True,
    )
    feed_item = target(
        "头条极速版随机文章",
        query_locator(
            "文章卡片ID",
            priority=10,
            options={"resource_id": prefix + "adk", "clickable": True, "pick": "random"},
        ),
        query_locator(
            "文章描述",
            priority=20,
            options={"contains_desc": "文章", "clickable": True, "pick": "random"},
        ),
        coordinate_locator("信息流首条文章坐标", Point(0.50, 0.44)),
        required=True,
    )
    task_entry = target(
        "头条极速版任务入口",
        text_locator("任务底栏文本", "任务", region=Rect(0.35, 0.88, 0.65, 1.0)),
        ocr_locator("任务底栏OCR", "任务", mode="exact", region=Rect(0.30, 0.88, 0.70, 1.0)),
        coordinate_locator("任务底栏坐标", Point(0.50, 0.97)),
        required=True,
    )
    task_marker = target(
        "头条极速版任务页标记",
        text_locator("看文章或视频文本", "看文章或视频", contains=True),
        text_locator("现金收益文本", "现金收益", priority=21),
        ocr_locator("看文章或视频OCR", "看文章或视频", confidence=0.45),
        required=True,
    )
    detail_marker = target(
        "头条极速版文章详情",
        text_locator("友善评论文本", "友善评论"),
        ocr_locator(
            "友善评论OCR",
            "友善评论",
            region=Rect(0.02, 0.78, 0.60, 0.98),
            confidence=0.45,
        ),
        query_locator("评论数量描述", options={"contains_desc": "评论"}, priority=21),
        required=True,
    )
    ad_close = target(
        "头条极速版广告关闭",
        desc_locator("广告关闭描述", "关闭"),
        text_locator("广告关闭文本", "关闭", priority=21),
        coordinate_locator("广告右上角关闭坐标", Point(0.94, 0.06)),
    )
    ad = AdSpec(
        start_markers=(
            text_target("头条极速版广告倒计时", "秒后可领奖励", contains=True),
            text_target("头条极速版激励广告", "广告", contains=True),
        ),
        completion_markers=(
            text_target("头条极速版广告到账", "领取成功", contains=True),
            text_target("头条极速版广告奖励", "奖励已到账", contains=True),
        ),
        continue_targets=(),
        next_sequences=(),
        close_targets=(ad_close,),
        final_close_targets=(ad_close,),
        exit_targets=(task_marker, home_tab),
        exit_after_wait_with_back=True,
        completion_wait_seconds=35.0,
    )

    return AppSpec(
        identity=AppIdentity("toutiao_lite", package_name, "今日头条极速版", "1.0.0"),
        display_name="今日头条极速版",
        navigation=NavigationSpec(
            home_marker=home_marker,
            home_tab=home_tab,
            task_entry=task_entry,
            task_marker=task_marker,
            reselect_home_tab=True,
            home_page=PageSpec(
                "toutiao_lite.home",
                package_name,
                (home_marker,),
                activity_patterns=(r"SplashActivity$",),
                observation_profile=profile,
            ),
            task_page=PageSpec(
                "toutiao_lite.task",
                package_name,
                (task_marker,),
                observation_profile=profile,
            ),
        ),
        check_in=None,
        balance=BalanceSpec(
            assets=(
                BalanceAssetSpec(
                    "cash",
                    "现金",
                    target(
                        "头条极速版现金余额",
                        ocr_locator(
                            "现金余额OCR",
                            r"\d+(?:\.\d+)?\s*元",
                            mode="regex",
                            region=Rect(0.03, 0.15, 0.30, 0.23),
                            confidence=0.25,
                        ),
                    ),
                    scale=2,
                    unit="元",
                ),
                BalanceAssetSpec(
                    "coin",
                    "金币",
                    target(
                        "头条极速版金币余额",
                        ocr_locator(
                            "金币余额OCR",
                            r"金币\s*\d+",
                            mode="regex",
                            region=Rect(0.03, 0.20, 0.30, 0.27),
                            confidence=0.25,
                        ),
                    ),
                    unit="金币",
                ),
            ),
        ),
        withdrawal=WithdrawalSpec(
            entry_sequence=(
                target(
                    "头条极速版收益详情入口",
                    text_locator("现金收益入口文本", "现金收益", contains=True),
                    coordinate_locator("顶部现金区域坐标", Point(0.16, 0.18)),
                ),
                target(
                    "头条极速版提现入口",
                    text_locator("去提现按钮文本", "去提现"),
                    ocr_locator("去提现按钮OCR", "去提现", mode="exact", confidence=0.45),
                ),
            ),
            available_region=Rect(0.27, 0.20, 0.72, 0.38),
            minimum_region=Rect(0.03, 0.42, 0.95, 0.67),
            close_back_count=2,
        ),
        ad=ad,
        ad_entry=target(
            "头条极速版广告奖励入口",
            text_locator("看广告赚金币文本", "看广告赚金币", contains=True),
            ocr_locator("看广告赚金币OCR", "看广告赚金币", confidence=0.45),
        ),
        duration_reward=DurationRewardSpec(
            reward_target=target(
                "头条极速版宝箱奖励",
                text_locator("开宝箱得金币文本", "开宝箱得金币"),
                ocr_locator(
                    "开宝箱得金币OCR",
                    "开宝箱得金币",
                    region=Rect(0.70, 0.75, 1.0, 0.92),
                    confidence=0.45,
                ),
            ),
            success_target=target(
                "头条极速版宝箱到账",
                text_locator("宝箱奖励文本", "宝箱奖励", contains=True),
                text_locator("恭喜获得文本", "恭喜获得", contains=True, priority=21),
                ocr_locator("恭喜获得OCR", "恭喜获得", confidence=0.45),
            ),
            close_target=target(
                "头条极速版宝箱结果关闭",
                coordinate_locator("宝箱结果底部关闭坐标", Point(0.50, 0.81)),
            ),
        ),
        content=NewsContentSpec(
            feed_item=feed_item,
            detail_marker=detail_marker,
            like_target=target("头条极速版点赞", desc_locator("点赞描述", "赞")),
            comment_target=target(
                "头条极速版查看评论",
                query_locator("评论入口描述", options={"contains_desc": "评论"}),
            ),
        ),
        observation_profile=profile,
    )


@dataclass(frozen=True, slots=True)
class ToutiaoNovelBonusTask:
    """领取任务页中短时、高收益的小说阅读奖励。"""

    go_task_page: TaskPagePopupNavigator

    def run(self, context: AppContext) -> StepOutcome:
        probability = float(context.option("novel_bonus_probability", 0.45))
        if context.random.random() >= probability:
            return StepOutcome.skipped("本轮随机跳过小说奖励")
        if not self.go_task_page(context):
            message = "小说奖励前无法进入任务页"
            context.emit(
                "reward.optional.unavailable",
                "奖励任务暂不可用",
                message,
                level=EventLevel.WARNING,
                workflow_id="daily",
                step_id="小说奖励",
                status="skipped",
            )
            return StepOutcome.skipped(message)
        entry = target(
            "头条极速版小说奖励入口",
            text_locator("看小说赚金币文本", "看小说赚金币", contains=True),
            ocr_locator("看小说赚金币OCR", "看小说赚金币", confidence=0.45),
        )
        if not context.actions.tap_target(entry, timeout=1.5):
            context.actions.swipe_up()
            context.timing.operation_delay()
            if not context.actions.tap_target(entry, timeout=1.5):
                return StepOutcome.skipped("当前没有小说奖励入口")
        seconds = context.sample_seconds(
            "novel_bonus_seconds",
            35.0,
            55.0,
            default_center=42.0,
            reward_wait=True,
        )
        context.timing.clock.sleep(seconds)
        context.actions.swipe_up()
        context.timing.operation_delay()
        context.actions.press(SystemKey.BACK)
        return StepOutcome.success("小说奖励浏览完成", viewed_seconds=round(seconds, 2))


@dataclass(frozen=True, slots=True)
class ToutiaoPendingRewardTask:
    """领取任务页中已经达标的两个时长红包。"""

    go_task_page: TaskPagePopupNavigator

    def run(self, context: AppContext) -> StepOutcome:
        pending = target(
            "头条极速版待领取时长红包",
            text_locator(
                "待领取文本",
                "待领取",
                region=Rect(0.03, 0.62, 0.36, 0.77),
            ),
            ocr_locator(
                "待领取OCR",
                "待领取",
                region=Rect(0.03, 0.62, 0.36, 0.77),
                confidence=0.45,
            ),
        )
        claimed = 0
        for _ in range(2):
            if not self.go_task_page(context):
                break
            if not context.actions.tap_target(pending, timeout=1.5):
                break
            claimed += 1
            context.timing.operation_delay()
            context.actions.press(SystemKey.BACK)
            context.timing.operation_delay()
        if claimed == 0:
            return StepOutcome.skipped("当前没有已达标的时长红包")
        return StepOutcome.success("时长红包领取完成", claimed_count=claimed)


def _task_popups() -> tuple[PopupDismissSpec, ...]:
    return (
        PopupDismissSpec(
            marker=text_target("头条极速版宝箱弹窗", "宝箱奖励", contains=True),
            close_target=target(
                "头条极速版宝箱弹窗关闭",
                coordinate_locator("宝箱弹窗底部关闭坐标", Point(0.50, 0.81)),
            ),
        ),
        PopupDismissSpec(
            marker=text_target("头条极速版答题弹窗", "每日答题赚金币", contains=True),
            close_target=target(
                "头条极速版答题弹窗关闭",
                coordinate_locator("答题弹窗底部关闭坐标", Point(0.50, 0.77)),
            ),
        ),
        PopupDismissSpec(
            marker=text_target("头条极速版邀请码弹窗", "输入邀请码", contains=True),
            close_target=target(
                "头条极速版邀请码弹窗关闭",
                coordinate_locator("邀请码弹窗右上角关闭坐标", Point(0.92, 0.38)),
            ),
        ),
    )


def create_plugin() -> ComposedAppPlugin:
    spec = toutiao_lite_spec()
    navigation = NavigationController(spec)
    task_page = TaskPagePopupNavigator(navigation, _task_popups())
    novel = ToutiaoNovelBonusTask(task_page)
    pending = ToutiaoPendingRewardTask(task_page)
    return create_daily_plugin(
        spec,
        navigation=navigation,
        task_page_navigator=task_page,
        extra_steps=lambda _: (
            StepDefinition(
                "领取时长红包",
                "领取已达标时长红包",
                pending.run,
                recovery=navigation.recover_home,
                task_scope=TaskScope.FULL_ONLY,
            ),
            StepDefinition(
                "小说奖励",
                "浏览小说奖励",
                novel.run,
                recovery=navigation.recover_home,
                task_scope=TaskScope.FULL_ONLY,
            ),
        ),
    )
