"""
喜番业务核对说明

每日流程：启动 -> 签到/刷短剧随机先后 -> 主动领取悬浮宝箱 -> 领取已达标直接奖励 -> 记录余额。

任务与限制：
- 主线浏览竖屏短剧，不执行点赞、评论、分享和关注。
- 首页通过右侧福利挂件进入福利中心；签到点击左侧“可领取”红包，避开右侧悬浮宝箱。
- 只领取明确显示“可领取/直接领”的奖励，不点击提现、下载、抽奖、邀请或添加桌面。

页面与状态标记：
- 首页 Activity 为 HomeActivity，短剧播放容器 ID 为 ksad_video_container。
- 福利页 Activity 为 WelfareActivityProxy，根节点 ID 为 welfare_root。
- 宝箱悬浮层显示“领N金币”，签到完成弹层显示“已签1/7天”。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from hym.apps.plugin import (
    ComposedAppPlugin,
    create_daily_plugin,
    create_daily_task_set,
)
from hym.apps.specs import (
    AppSpec,
    BalanceAssetSpec,
    BalanceSpec,
    CheckInSpec,
    CheckInStageSpec,
    DurationRewardSpec,
    InteractionSpec,
    NavigationSpec,
    VideoContentSpec,
    WithdrawalSpec,
)
from hym.apps.targets import (
    coordinate_locator,
    id_locator,
    ocr_locator,
    regex_locator,
    target,
    text_locator,
)
from hym.core.control import TaskScope
from hym.core.models import (
    AppIdentity,
    Point,
    Rect,
    SystemKey,
    UiTreeSource,
    WorkflowStatus,
)
from hym.core.pages import ObservationProfile, PageSpec
from hym.runtime.context import AppContext
from hym.runtime.navigation import NavigationController
from hym.runtime.rewards import BalanceTask
from hym.runtime.workflow import StepDefinition, StepOutcome


def xifan_theater_spec() -> AppSpec:
    package_name = "com.kwai.theater"
    prefix = f"{package_name}:id/"
    profile = ObservationProfile(UiTreeSource.APPLICATION)

    feed_marker = target(
        "喜番短剧流标记",
        id_locator("视频容器ID", prefix + "ksad_video_container"),
        id_locator("播放容器ID", prefix + "play_container", priority=11),
        id_locator("短剧标题ID", prefix + "ksad_bottom_content_describe", priority=12),
        required=True,
    )
    home_tab = target(
        "喜番短剧首页恢复目标",
        id_locator("视频容器恢复ID", prefix + "ksad_video_container"),
        coordinate_locator("短剧画面坐标", Point(0.50, 0.55)),
        required=True,
    )
    task_entry = target(
        "喜番福利入口",
        id_locator("福利挂件文字ID", prefix + "welfare_pendant_bottom_text"),
        text_locator("点击领取文本", "点击领取", priority=20),
        id_locator("福利挂件根节点ID", prefix + "float_root", priority=21),
        required=True,
    )
    task_marker = target(
        "喜番福利中心标记",
        id_locator("福利页根节点ID", prefix + "welfare_root"),
        text_locator("福利中心标题", "福利中心", priority=20),
        text_locator("金币凌晨兑现文本", "金币(凌晨自动兑现)", priority=21),
        required=True,
    )

    return AppSpec(
        identity=AppIdentity("xifan_theater", package_name, "喜番", "3.9.3.2"),
        display_name="喜番",
        navigation=NavigationSpec(
            home_marker=feed_marker,
            home_tab=home_tab,
            task_entry=task_entry,
            task_marker=task_marker,
            reselect_home_tab=False,
            select_home_tab_before_task=False,
            home_page=PageSpec(
                "xifan_theater.home",
                package_name,
                (feed_marker,),
                observation_profile=profile,
            ),
            task_page=PageSpec(
                "xifan_theater.task",
                package_name,
                (task_marker,),
                activity_patterns=(r"WelfareActivityProxy$",),
                observation_profile=profile,
            ),
        ),
        check_in=CheckInSpec(
            stages=(
                CheckInStageSpec(
                    "领取七日签到",
                    (
                        target(
                            "喜番首日签到红包",
                            text_locator(
                                "可领取文本",
                                "可领取",
                                region=Rect(0.05, 0.65, 0.25, 0.95),
                            ),
                        ),
                    ),
                ),
            ),
            success_targets=(
                target(
                    "喜番签到到账",
                    text_locator("已签天数文本", "已签", contains=True),
                    text_locator("签到金币弹层文本", "金币", contains=True, priority=30),
                    required=True,
                ),
            ),
            passive_success_targets=(
                target(
                    "喜番今日签到完成",
                    text_locator("已领取文本", "已领取"),
                    text_locator("今日已签到文本", "今日已签到", contains=True, priority=21),
                ),
            ),
            # 已签到页面没有弹层，不能无条件点击屏幕下方的关闭坐标。
            close_target=None,
        ),
        balance=BalanceSpec(
            assets=(
                BalanceAssetSpec(
                    "coin",
                    "金币",
                    target(
                        "喜番金币余额",
                        ocr_locator(
                            "金币余额OCR",
                            r"\d+",
                            mode="regex",
                            region=Rect(0.05, 0.12, 0.43, 0.27),
                            confidence=0.4,
                        ),
                    ),
                    unit="金币",
                ),
                BalanceAssetSpec(
                    "cash",
                    "现金",
                    target(
                        "喜番现金余额",
                        text_locator(
                            "现金零余额文本",
                            "0",
                            region=Rect(0.43, 0.12, 0.70, 0.27),
                        ),
                        ocr_locator(
                            "现金余额OCR",
                            r"\d+(?:\.\d+)?",
                            mode="regex",
                            region=Rect(0.43, 0.12, 0.70, 0.27),
                            confidence=0.4,
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
                    "喜番提现入口",
                    text_locator("领现金文本", "领现金"),
                    ocr_locator(
                        "领现金OCR",
                        "领现金",
                        mode="exact",
                        region=Rect(0.65, 0.10, 0.98, 0.24),
                        confidence=0.4,
                    ),
                ),
            ),
            available_region=Rect(0.05, 0.11, 0.42, 0.23),
            minimum_region=Rect(0.04, 0.28, 0.96, 0.53),
        ),
        ad=None,
        ad_entry=None,
        duration_reward=DurationRewardSpec(
            reward_target=target(
                "喜番宝箱奖励",
                regex_locator(
                    "宝箱领金币文本",
                    r"领\d+金币",
                    region=Rect(0.72, 0.65, 1.0, 0.92),
                ),
            ),
            success_target=target(
                "喜番宝箱到账",
                text_locator("开宝箱奖励文本", "开宝箱奖励"),
                ocr_locator("开宝箱奖励OCR", "开宝箱奖励", confidence=0.45),
                regex_locator(
                    "宝箱冷却倒计时",
                    r"\d{2}:\d{2}领金币",
                    region=Rect(0.70, 0.65, 1.0, 0.92),
                    priority=31,
                ),
                ocr_locator(
                    "宝箱冷却倒计时OCR",
                    r"\d{2}:\d{2}领金币",
                    mode="regex",
                    region=Rect(0.70, 0.65, 1.0, 0.92),
                    confidence=0.4,
                    priority=81,
                ),
            ),
            close_target=target(
                "喜番宝箱弹层关闭",
                coordinate_locator("宝箱弹层关闭坐标", Point(0.50, 0.80)),
            ),
            result_wait_seconds=2.0,
        ),
        content=VideoContentSpec(
            feed_marker=feed_marker,
            ad_markers=(
                target(
                    "喜番短剧广告标记",
                    text_locator("广告文本", "广告", contains=True),
                    text_locator("立即下载文本", "立即下载", contains=True, priority=21),
                    text_locator("查看详情文本", "查看详情", contains=True, priority=22),
                ),
            ),
            normal_markers=(feed_marker,),
            long_markers=(
                target(
                    "喜番长内容标记",
                    id_locator("选集入口ID", prefix + "episode_enter_bar"),
                    text_locator("全剧集文本", "全", contains=True, priority=21),
                ),
            ),
            interaction=InteractionSpec(),
        ),
        observation_profile=profile,
    )


@dataclass(frozen=True, slots=True)
class XifanDirectRewardTask:
    """领取页面中已经达标的直接金币，不触碰看广告、抽奖和下载任务。"""

    navigation: NavigationController

    def run(self, context: AppContext) -> StepOutcome:
        # 本步骤紧跟宝箱，当前已经位于福利中心。不要再次导航：奖励弹层消失时
        # 页面树会短暂重建，通用导航可能把它误判成异常 Activity。
        reward = target(
            "喜番已达标直接奖励",
            regex_locator("直接领金币文本", r"直接领\d+", region=Rect(0.05, 0.20, 0.75, 0.95)),
        )
        claimed = 0
        for attempt in range(4):
            if context.actions.tap_target(reward, timeout=1.0):
                claimed += 1
                context.timing.operation_delay()
                context.actions.press(SystemKey.BACK)
                context.timing.operation_delay()
                continue
            if attempt < 3:
                context.actions.swipe_up()
                context.timing.operation_delay()
        if claimed == 0:
            return StepOutcome.skipped("当前没有已达标的直接金币奖励")
        return StepOutcome.success("喜番直接金币奖励领取完成", claimed_count=claimed)


@dataclass(frozen=True, slots=True)
class XifanFreshBalanceTask:
    """从首页重新进入福利中心，避免下滚后的任务金额被当成顶部余额。"""

    spec: AppSpec
    navigation: NavigationController

    def run(self, context: AppContext) -> StepOutcome:
        if context.daily_value("balance") is not None:
            return StepOutcome(WorkflowStatus.ALREADY_DONE, "今天已经记录过余额")
        self.navigation.recover_home(context)
        if not self.navigation.go_task_page(context):
            return StepOutcome.failure("记录余额时无法重新进入喜番福利中心")
        for _ in range(4):
            context.actions.swipe_down()
            context.timing.operation_delay()
        return BalanceTask(self.spec, lambda _: True).run(context)


def create_plugin() -> ComposedAppPlugin:
    spec = xifan_theater_spec()
    navigation = NavigationController(spec)
    tasks = create_daily_task_set(spec, navigation=navigation)
    tasks = replace(tasks, balance=XifanFreshBalanceTask(spec, navigation).run)
    direct_reward = XifanDirectRewardTask(navigation)
    return create_daily_plugin(
        spec,
        navigation=navigation,
        tasks=tasks,
        extra_steps=lambda _: (
            StepDefinition(
                "领取直接奖励",
                "领取已达标直接金币奖励",
                direct_reward.run,
                recovery=navigation.recover_home,
                task_scope=TaskScope.FULL_ONLY,
            ),
        ),
    )
