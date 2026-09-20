"""
百度极速版业务核对说明

每日流程：启动 -> 签到/刷视频随机先后 -> 领取任务页宝箱 -> 按概率看奖励广告 -> 记录余额和提现门槛。

任务与限制：
- 文章和视频共用时长奖励，当前选择入口稳定、连续操作更少的视频主线。
- 普通视频按配置停留；明确广告或下载推广快速划过且不互动。
- 签到、广告失败只影响各自步骤；已达标红包和任务页右下角宝箱会在任务页限量领取。

页面与状态标记：
- 视频页 Activity 为 VideoTabActivity，并显示“下一条”；主页底栏入口为“视频”。
- 任务页包含“任务系统/看文章视频”；先退出沉浸视频流，再点主页面底栏中央金币入口。
- 新版控件变化优先在本文件补标记；底栏坐标只作为当前版本末级入口。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from hym.apps.app_specs.common import TaskPagePopupNavigator, text_target
from hym.apps.plugin import (
    ComposedAppPlugin,
    create_daily_plugin,
    create_daily_task_set,
)
from hym.apps.specs import (
    AdSpec,
    AppSpec,
    BalanceAssetSpec,
    BalanceSpec,
    CheckInSpec,
    CheckInStageSpec,
    InteractionSpec,
    NavigationSpec,
    PopupDismissSpec,
    VideoContentSpec,
    WithdrawalSpec,
)
from hym.apps.targets import (
    activity_locator,
    coordinate_locator,
    desc_locator,
    ocr_locator,
    regex_locator,
    target,
    text_locator,
)
from hym.core.control import TaskScope
from hym.core.models import AppIdentity, Point, Rect, SystemKey, UiTreeSource, WorkflowStatus
from hym.core.pages import ObservationProfile, PageSpec
from hym.runtime.ads import AdStateMachine
from hym.runtime.context import AppContext
from hym.runtime.navigation import NavigationController
from hym.runtime.rewards import CheckInTask
from hym.runtime.workflow import StepDefinition, StepOutcome


def baidu_lite_spec() -> AppSpec:
    package_name = "com.baidu.searchbox.lite"
    profile = ObservationProfile(UiTreeSource.APPLICATION)

    video_page = target(
        "百度极速版视频页标记",
        activity_locator(
            "视频页Activity",
            r"VideoTabActivity$",
            package_name=package_name,
        ),
        text_locator("下一条文本", "下一条", contains=True, priority=20),
        text_locator("取消静音文本", "取消静音", priority=21),
        text_locator("全屏观看文本", "全屏观看", priority=22),
        required=True,
    )
    home_tab = target(
        "百度极速版视频入口",
        text_locator("视频底栏文本", "视频", region=Rect(0.10, 0.88, 0.45, 1.0)),
        ocr_locator(
            "视频底栏OCR",
            "视频",
            mode="exact",
            region=Rect(0.10, 0.88, 0.45, 1.0),
            confidence=0.45,
        ),
        coordinate_locator("视频底栏坐标", Point(0.30, 0.97)),
        required=True,
    )
    bottom_bar = target(
        "百度极速版主页面底栏",
        text_locator("百度底栏文本", "百度", region=Rect(0.0, 0.88, 0.24, 1.0)),
        text_locator("我的底栏文本", "我的", region=Rect(0.76, 0.88, 1.0, 1.0), priority=21),
        ocr_locator(
            "百度底栏OCR",
            "百度",
            mode="exact",
            region=Rect(0.0, 0.88, 0.24, 1.0),
            confidence=0.45,
        ),
        required=True,
    )
    task_entry = target(
        "百度极速版任务入口",
        desc_locator("金币挂件描述", "金币"),
        # 当前版本从底栏中央金币按钮进入任务页；旧版若恢复描述仍优先使用描述定位。
        coordinate_locator("底栏中央金币入口坐标", Point(0.50, 0.96)),
        required=True,
    )
    task_marker = target(
        "百度极速版任务页标记",
        text_locator("金币收益文本", "金币收益", contains=True),
        text_locator("今日签到文本", "今日签到", contains=True, priority=21),
        text_locator("精选福利文本", "精选福利", contains=True, priority=22),
        text_locator("看文章视频文本", "看文章视频", contains=True, priority=23),
        ocr_locator("金币收益OCR", "金币收益", mode="contains", confidence=0.45),
        ocr_locator("精选福利OCR", "精选福利", mode="contains", confidence=0.45, priority=81),
        required=True,
    )
    ad_close = target(
        "百度极速版广告关闭",
        desc_locator("广告关闭描述", "关闭"),
        text_locator("广告关闭文本", "关闭", priority=21),
        coordinate_locator("广告右上角关闭坐标", Point(0.93, 0.085)),
    )
    ad = AdSpec(
        start_markers=(
            target(
                "百度极速版新版激励广告页",
                activity_locator(
                    "新版激励广告Activity",
                    r"NadRewardVideoActivityV2$",
                    package_name=package_name,
                ),
            ),
            text_target("百度极速版广告倒计时", "秒后可领奖励", contains=True),
            target(
                "百度极速版金币广告倒计时",
                ocr_locator(
                    "金币广告倒计时OCR",
                    r"\d+s后可领\d+金币",
                    mode="regex",
                    region=Rect(0.0, 0.03, 0.48, 0.16),
                    confidence=0.45,
                ),
            ),
            text_target("百度极速版激励广告", "广告", contains=True),
        ),
        completion_markers=(
            text_target("百度极速版广告到账", "领取成功", contains=True),
            text_target("百度极速版广告奖励获得", "已获得", contains=True),
            text_target("百度极速版广告金币已领取", "已领取", contains=True),
            text_target("百度极速版广告体验提示", "打开应用并体验", contains=True),
        ),
        continue_targets=(),
        next_sequences=(),
        close_targets=(ad_close,),
        final_close_targets=(ad_close,),
        exit_targets=(task_marker, video_page),
        exit_after_wait_with_back=True,
        exit_prompt_markers=(text_target("百度极速版广告退出提示", "继续完成任务"),),
        exit_prompt_close_targets=(text_target("百度极速版广告残忍离开", "残忍离开"),),
        completion_wait_seconds=35.0,
    )

    tutorial = PopupDismissSpec(
        marker=text_target("百度极速版视频引导", "上滑查看下条视频", contains=True),
        close_target=text_target("百度极速版视频引导确认", "我知道了"),
    )
    return AppSpec(
        identity=AppIdentity("baidu_lite", package_name, "百度极速版", "1.0.0"),
        display_name="百度极速版",
        navigation=NavigationSpec(
            # 主页面与沉浸视频流分开判断，任务入口只存在于带底栏的主页面。
            home_marker=bottom_bar,
            home_tab=home_tab,
            task_entry=task_entry,
            task_marker=task_marker,
            launch_intercepts=(tutorial,),
            home_intercepts=(tutorial,),
            reselect_home_tab=True,
            select_home_tab_before_task=False,
            home_page=PageSpec(
                "baidu_lite.main",
                package_name,
                (bottom_bar,),
                activity_patterns=(r"MainActivity$",),
                observation_profile=profile,
            ),
            task_page=PageSpec(
                "baidu_lite.task",
                package_name,
                (task_marker,),
                observation_profile=profile,
            ),
        ),
        check_in=CheckInSpec(
            stages=(
                CheckInStageSpec(
                    "打开签到面板",
                    (
                        target(
                            "百度极速版签到按钮",
                            text_locator("去签到文本", "去签到"),
                            text_locator("立即签到文本", "立即签到", priority=21),
                            ocr_locator("去签到OCR", "去签到", confidence=0.45),
                        ),
                    ),
                    commit_action=False,
                ),
                CheckInStageSpec(
                    "领取今日奖励",
                    (
                        target(
                            "百度极速版领取今日奖励",
                            text_locator("领取今日奖励文本", "领取今日奖励"),
                            ocr_locator(
                                "领取今日奖励OCR",
                                "领取今日奖励",
                                mode="exact",
                                region=Rect(0.15, 0.62, 0.85, 0.78),
                                confidence=0.45,
                            ),
                        ),
                    ),
                ),
            ),
            success_targets=(
                target(
                    "百度极速版签到成功",
                    text_locator("签到奖励文本", "今日签到+", contains=True),
                    text_locator("已签到文本", "已签到", contains=True),
                    text_locator("明日再来文本", "明日再来", priority=21),
                    regex_locator("连续签到天数", r"连续签到[1-9]\d*天", priority=22),
                    ocr_locator(
                        "下次签到OCR",
                        "明天",
                        mode="exact",
                        region=Rect(0.20, 0.42, 0.60, 0.56),
                        confidence=0.45,
                        priority=81,
                    ),
                    ocr_locator(
                        "签到奖励OCR",
                        r"今日签到\+\d+金币",
                        mode="regex",
                        confidence=0.45,
                    ),
                    required=True,
                ),
            ),
            close_target=target(
                "百度极速版签到奖励直接领取",
                text_locator("直接领取文本", "直接领取"),
                ocr_locator("直接领取OCR", "直接领取", mode="exact", confidence=0.45),
            ),
        ),
        balance=BalanceSpec(
            assets=(
                BalanceAssetSpec(
                    "cash",
                    "现金",
                    target(
                        "百度极速版现金余额",
                        ocr_locator(
                            "现金余额OCR",
                            r"\d+(?:\.\d+)?",
                            mode="regex",
                            region=Rect(0.36, 0.09, 0.68, 0.17),
                            confidence=0.4,
                        ),
                    ),
                    scale=2,
                    unit="元",
                ),
                BalanceAssetSpec(
                    "coin",
                    "金币",
                    target(
                        "百度极速版金币余额",
                        ocr_locator(
                            "金币余额OCR",
                            r"\d+(?:\.\d+)?",
                            mode="regex",
                            region=Rect(0.04, 0.09, 0.36, 0.17),
                            confidence=0.4,
                        ),
                    ),
                    unit="金币",
                ),
            ),
        ),
        withdrawal=WithdrawalSpec(
            entry_sequence=(
                target(
                    "百度极速版提现入口",
                    text_locator("去提现按钮文本", "去提现"),
                    ocr_locator(
                        "去提现按钮OCR",
                        "去提现",
                        mode="exact",
                        region=Rect(0.68, 0.08, 1.0, 0.22),
                        confidence=0.45,
                    ),
                ),
            ),
            available_region=Rect(0.25, 0.12, 0.72, 0.25),
            minimum_region=Rect(0.03, 0.30, 0.95, 0.72),
            details_region=Rect(0.03, 0.27, 0.97, 0.90),
        ),
        ad=ad,
        ad_entry=target(
            "百度极速版广告奖励入口",
            text_locator("看广告赚钱文本", "看广告赚钱", contains=True),
            ocr_locator("看广告赚钱OCR", "看广告赚钱", confidence=0.45),
        ),
        duration_reward=None,
        content=VideoContentSpec(
            feed_marker=video_page,
            ad_markers=(
                text_target("百度极速版视频广告标记", "广告", contains=True),
                text_target("百度极速版视频下载标记", "立即下载", contains=True),
                text_target("百度极速版视频详情标记", "查看详情", contains=True),
            ),
            normal_markers=(video_page,),
            long_markers=(text_target("百度极速版长视频标记", "选集", contains=True),),
            interaction=InteractionSpec(),
        ),
        observation_profile=profile,
    )


@dataclass(frozen=True, slots=True)
class BaiduCheckInNavigator:
    """签到位于任务页下方，仅签到任务按需滚动一次。"""

    spec: AppSpec
    task_page: TaskPagePopupNavigator

    def __call__(self, context: AppContext) -> bool:
        if not self.task_page(context):
            return False
        check_in = self.spec.check_in
        if check_in is None:
            return False
        targets = tuple(check_in.success_targets) + tuple(
            target for stage in check_in.stages for target in stage.action_targets
        )
        if context.actions.resolve_many(
            targets,
            include_screenshot=context.actions.needs_screenshot(targets),
        ) is not None:
            return True
        context.actions.swipe_up()
        context.timing.operation_delay()
        return True


@dataclass(frozen=True, slots=True)
class BaiduChestRewardTask:
    """处理任务页右下角宝箱及当前版本的二选一奖励。"""

    spec: AppSpec
    task_page: TaskPagePopupNavigator

    def run(self, context: AppContext) -> StepOutcome:
        if not self.task_page(context):
            return StepOutcome.failure("领取百度宝箱时无法进入任务页")
        chest = target(
            "百度极速版任务页右下角宝箱",
            text_locator("宝箱奖励文本", "点击宝箱领奖励"),
            ocr_locator(
                "宝箱奖励OCR",
                "点击宝箱领奖励",
                region=Rect(0.72, 0.72, 1.0, 0.92),
                confidence=0.45,
            ),
        )
        if not context.actions.tap_target(chest, timeout=1.5):
            return StepOutcome.skipped("当前没有可领取的百度宝箱")
        context.timing.operation_delay()

        video_choice = target(
            "百度极速版看视频宝箱",
            text_locator("选择999金币文本", "选999金币"),
            text_locator("看视频开宝箱文本", "看视频开宝箱", priority=21),
            ocr_locator("选择999金币OCR", "选999金币", confidence=0.45),
            coordinate_locator("看视频宝箱坐标", Point(0.73, 0.57)),
        )
        if not context.actions.tap_target(video_choice, timeout=2.0):
            return StepOutcome.failure("宝箱已打开，但没有匹配到奖励选择")
        context.timing.operation_delay()
        if self.spec.ad is None:
            return StepOutcome.failure("百度宝箱缺少广告处理规格")
        outcome = AdStateMachine().run(context, self.spec.ad)
        if outcome.status is WorkflowStatus.SUCCESS:
            context.record_reward(
                "baidu_chest",
                "百度任务页宝箱奖励已确认",
                workflow_id="daily",
                step_id="领取任务页宝箱",
            )
            return StepOutcome.success("百度任务页宝箱领取完成")
        if outcome.status is WorkflowStatus.PARTIAL:
            return StepOutcome(
                WorkflowStatus.PARTIAL,
                "百度宝箱广告已观看，但到账状态未完全确认",
                {"ad_message": outcome.message},
            )
        return StepOutcome.failure("百度宝箱广告没有完成")


@dataclass(frozen=True, slots=True)
class BaiduPendingRewardTask:
    """只领取“看文章视频”一栏中已经达标的红包。"""

    task_page: TaskPagePopupNavigator

    def run(self, context: AppContext) -> StepOutcome:
        pending = target(
            "百度极速版已达标内容红包",
            text_locator(
                "内容红包待领取文本",
                "待领取",
                region=Rect(0.05, 0.52, 0.52, 0.68),
            ),
            ocr_locator(
                "内容红包待领取OCR",
                "待领取",
                mode="exact",
                region=Rect(0.05, 0.52, 0.52, 0.68),
                confidence=0.45,
            ),
        )
        claimed = 0
        for _ in range(3):
            if not self.task_page(context):
                break
            if not context.actions.tap_target(pending, timeout=1.5):
                break
            claimed += 1
            context.timing.operation_delay()
            context.actions.press(SystemKey.BACK)
            context.timing.operation_delay()
        if claimed == 0:
            return StepOutcome.skipped("当前没有已达标的内容红包")
        return StepOutcome.success("已达标内容红包领取完成", claimed_count=claimed)


def create_plugin() -> ComposedAppPlugin:
    spec = baidu_lite_spec()
    navigation = NavigationController(spec)
    automatic_reward = PopupDismissSpec(
        marker=text_target("百度极速版自动奖励弹窗", "恭喜获得", contains=True),
        close_target=target(
            "百度极速版自动奖励弹窗关闭",
            coordinate_locator("自动奖励右上角关闭坐标", Point(0.82, 0.335)),
        ),
    )
    check_in_reward = PopupDismissSpec(
        marker=target(
            "百度极速版签到奖励弹窗",
            text_locator("今日签到奖励文本", "今日签到+", contains=True),
            ocr_locator("今日签到奖励OCR", "今日签到+", confidence=0.45),
        ),
        # 奖励已经达标时直接领取，不额外观看加倍广告。
        close_target=target(
            "百度极速版签到奖励直接领取",
            text_locator("直接领取文本", "直接领取"),
            ocr_locator("直接领取OCR", "直接领取", mode="exact", confidence=0.45),
        ),
    )
    notification_popup = PopupDismissSpec(
        marker=target(
            "百度极速版金币通知弹窗",
            text_locator("订阅金币通知文本", "订阅金币通知", contains=True),
            ocr_locator("订阅金币通知OCR", "订阅金币通知", confidence=0.45),
        ),
        close_target=target(
            "百度极速版金币通知暂不订阅",
            text_locator("我再想想文本", "我再想想"),
            ocr_locator("我再想想OCR", "我再想想", mode="exact", confidence=0.45),
        ),
    )
    treasure_popup = PopupDismissSpec(
        marker=target(
            "百度极速版寻宝弹窗",
            text_locator("寻宝得现金文本", "寻宝得现金", contains=True),
            ocr_locator("寻宝得现金OCR", "寻宝得现金", confidence=0.45),
        ),
        close_target=target(
            "百度极速版寻宝弹窗关闭",
            coordinate_locator("寻宝弹窗右上角关闭坐标", Point(0.87, 0.195)),
        ),
    )
    newcomer_popup = PopupDismissSpec(
        marker=target(
            "百度极速版七天新人奖励弹窗",
            text_locator("开心收下文本", "开心收下"),
            ocr_locator("开心收下OCR", "开心收下", mode="exact", confidence=0.45),
        ),
        close_target=target(
            "百度极速版七天新人奖励弹窗关闭",
            coordinate_locator("七天新人奖励右上角关闭坐标", Point(0.85, 0.255)),
        ),
    )
    coin_pool_popup = PopupDismissSpec(
        marker=target(
            "百度极速版瓜分金币弹窗",
            text_locator("瓜分百亿金币文本", "瓜分百亿金币", contains=True),
            ocr_locator("瓜分百亿金币OCR", "瓜分百亿金币", confidence=0.45),
        ),
        close_target=target(
            "百度极速版瓜分金币弹窗关闭",
            coordinate_locator("瓜分金币右上角关闭坐标", Point(0.89, 0.195)),
        ),
    )
    task_page = TaskPagePopupNavigator(
        navigation,
        (
            automatic_reward,
            check_in_reward,
            notification_popup,
            treasure_popup,
            newcomer_popup,
            coin_pool_popup,
        ),
        max_dismissals=6,
        check_after_entry=True,
    )
    pending = BaiduPendingRewardTask(task_page)
    chest = BaiduChestRewardTask(spec, task_page)
    tasks = create_daily_task_set(
        spec,
        navigation=navigation,
        task_page_navigator=task_page,
    )
    tasks = replace(
        tasks,
        check_in=CheckInTask(spec, BaiduCheckInNavigator(spec, task_page)).run,
    )
    return create_daily_plugin(
        spec,
        navigation=navigation,
        tasks=tasks,
        extra_steps=lambda _: (
            StepDefinition(
                "领取任务页宝箱",
                "领取任务页右下角宝箱",
                chest.run,
                recovery=navigation.recover_home,
                task_scope=TaskScope.FULL_ONLY,
            ),
            StepDefinition(
                "领取内容红包",
                "领取已达标内容红包",
                pending.run,
                recovery=navigation.recover_home,
                task_scope=TaskScope.FULL_ONLY,
            ),
        ),
    )
