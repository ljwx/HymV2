"""
河马剧场业务核对说明

每日流程：启动 -> 签到/刷短剧随机先后 -> 主动领取右下角宝箱 -> 记录余额。

任务与限制：
- 主线只浏览竖屏短剧；广告或下载推广只短暂停留，不执行点赞、评论和关注。
- 福利中心是 Web 内容，Poco 只能稳定读取页头和底栏，因此签到与余额保留 OCR 后备。
- 只领取签到和已到时宝箱，不点击提现、兑换、邀请好友或付费入口。

页面与状态标记：
- 首页 Activity 为 MainActivity，短剧容器 ID 为 container/root_textureview。
- 底栏中央“赚钱”进入福利中心，页头包含“福利中心/福利商城”。
- 宝箱入口是原生 boxTask_ll；签到到账弹层包含“恭喜你获得”。
"""

from __future__ import annotations

from dataclasses import replace

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
    PopupDismissSpec,
    VideoContentSpec,
    WithdrawalSpec,
)
from hym.apps.targets import (
    activity_locator,
    coordinate_locator,
    id_locator,
    ocr_locator,
    regex_locator,
    target,
    text_locator,
)
from hym.core.models import AppIdentity, Point, Rect, UiTreeSource
from hym.core.pages import ObservationProfile, PageSpec
from hym.runtime.navigation import NavigationController
from hym.runtime.rewards import BalanceTask, CheckInTask, DurationRewardTask, WithdrawalTask


def hema_theater_spec() -> AppSpec:
    package_name = "com.dz.hmjc"
    prefix = f"{package_name}:id/"
    profile = ObservationProfile(UiTreeSource.APPLICATION)

    home_tab = target(
        "河马剧场首页标签",
        text_locator("首页底栏文本", "首页", region=Rect(0.0, 0.90, 0.20, 1.0)),
        id_locator("首页底栏文字ID", prefix + "textView_only", priority=30),
        coordinate_locator("首页底栏坐标", Point(0.10, 0.96)),
        required=True,
    )
    feed_marker = target(
        "河马剧场短剧流标记",
        id_locator("短剧容器ID", prefix + "container"),
        id_locator("视频画面ID", prefix + "root_textureview", priority=11),
        id_locator("剧名ID", prefix + "tv_name_new", priority=12),
        required=True,
    )
    task_entry = target(
        "河马剧场赚钱入口",
        id_locator("赚钱图标ID", prefix + "iv_welfare_bottom"),
        ocr_locator(
            "赚钱底栏OCR",
            "赚钱",
            mode="exact",
            region=Rect(0.40, 0.90, 0.60, 1.0),
            confidence=0.45,
        ),
        coordinate_locator("赚钱底栏坐标", Point(0.50, 0.96)),
        required=True,
    )
    task_marker = target(
        "河马剧场福利中心标记",
        text_locator("福利中心页头文本", "福利中心"),
        text_locator("福利商城页头文本", "福利商城", priority=21),
        ocr_locator(
            "福利中心页头OCR",
            "福利中心",
            mode="exact",
            region=Rect(0.0, 0.04, 0.55, 0.15),
            confidence=0.45,
        ),
        required=True,
    )
    youth_mode = PopupDismissSpec(
        marker=target(
            "河马剧场青少年模式弹层",
            ocr_locator("青少年模式OCR", "青少年模式", confidence=0.45),
        ),
        close_target=target(
            "河马剧场青少年模式确认",
            coordinate_locator("我知道了坐标", Point(0.50, 0.91)),
        ),
    )
    pending_reward = PopupDismissSpec(
        marker=target(
            "河马剧场待领取奖励弹层",
            ocr_locator("待领取奖励OCR", "看短剧奖励待领取", confidence=0.45),
        ),
        close_target=target(
            "河马剧场待领取奖励关闭",
            coordinate_locator("待领取奖励关闭坐标", Point(0.855, 0.235)),
        ),
    )
    leave_player = PopupDismissSpec(
        marker=feed_marker,
        close_target=target(
            "河马剧场退出沉浸播放器",
            coordinate_locator("播放器左上角返回坐标", Point(0.055, 0.077)),
        ),
    )

    return AppSpec(
        identity=AppIdentity("hema_theater", package_name, "河马剧场", "3.11.1"),
        display_name="河马剧场",
        navigation=NavigationSpec(
            home_marker=feed_marker,
            home_tab=home_tab,
            task_entry=task_entry,
            task_marker=task_marker,
            launch_intercepts=(youth_mode, pending_reward),
            home_intercepts=(youth_mode, pending_reward, leave_player),
            reselect_home_tab=False,
            select_home_tab_before_task=False,
            home_page=PageSpec(
                "hema_theater.home",
                package_name,
                (feed_marker, home_tab),
                minimum_markers=2,
                observation_profile=profile,
            ),
            task_page=PageSpec(
                "hema_theater.task",
                package_name,
                (task_marker,),
                activity_patterns=(r"MainActivity$",),
                observation_profile=profile,
            ),
        ),
        check_in=CheckInSpec(
            stages=(
                CheckInStageSpec(
                    "领取新人签到",
                    (
                        target(
                            "河马剧场签到领取按钮",
                            ocr_locator(
                                "签到领取OCR",
                                "领取",
                                mode="exact",
                                region=Rect(0.72, 0.46, 0.98, 0.62),
                                confidence=0.45,
                            ),
                        ),
                    ),
                ),
            ),
            success_targets=(
                target(
                    "河马剧场签到到账",
                    ocr_locator("签到到账OCR", "恭喜你获得", confidence=0.45),
                    regex_locator("签到金币结果", r"\d+金币", priority=81),
                    required=True,
                ),
            ),
            passive_success_targets=(
                target(
                    "河马剧场今日签到完成",
                    ocr_locator(
                        "签到已完成OCR",
                        "已完成",
                        mode="exact",
                        region=Rect(0.70, 0.55, 0.98, 0.78),
                        confidence=0.45,
                    ),
                ),
            ),
            # 不声明无条件关闭坐标：页面已签到时没有弹层，坐标点击会误入提现任务。
            close_target=None,
        ),
        balance=BalanceSpec(
            assets=(
                BalanceAssetSpec(
                    "coin",
                    "金币",
                    target(
                        "河马剧场金币余额",
                        ocr_locator(
                            "金币余额OCR",
                            r"\d+",
                            mode="regex",
                            region=Rect(0.03, 0.12, 0.40, 0.23),
                            confidence=0.4,
                        ),
                    ),
                    unit="金币",
                ),
                BalanceAssetSpec(
                    "cash",
                    "现金",
                    target(
                        "河马剧场现金余额",
                        ocr_locator(
                            "现金余额OCR",
                            r"\d+(?:\.\d+)?",
                            mode="regex",
                            region=Rect(0.48, 0.12, 0.82, 0.23),
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
                    "河马剧场提现入口",
                    text_locator(
                        "顶部去提现文本",
                        "去提现",
                        region=Rect(0.65, 0.08, 0.98, 0.23),
                    ),
                    ocr_locator(
                        "顶部去提现OCR",
                        "去提现",
                        mode="exact",
                        region=Rect(0.65, 0.08, 0.98, 0.23),
                        confidence=0.4,
                    ),
                ),
            ),
            available_region=Rect(0.48, 0.11, 0.86, 0.23),
            minimum_region=Rect(0.04, 0.29, 0.96, 0.49),
        ),
        ad=None,
        ad_entry=None,
        duration_reward=DurationRewardSpec(
            reward_target=target(
                "河马剧场宝箱奖励",
                id_locator("宝箱入口ID", prefix + "boxTask_ll"),
                regex_locator("宝箱领取文本", r"点击领\d+金币", priority=21),
            ),
            success_target=target(
                "河马剧场宝箱到账",
                ocr_locator("开宝箱奖励OCR", "开宝箱奖励", confidence=0.45),
                ocr_locator("宝箱恭喜获得OCR", "恭喜获得开宝箱奖励", confidence=0.45),
            ),
            close_target=target(
                "河马剧场宝箱弹层关闭",
                coordinate_locator("宝箱弹层关闭坐标", Point(0.86, 0.18)),
            ),
            result_wait_seconds=2.0,
        ),
        content=VideoContentSpec(
            feed_marker=feed_marker,
            ad_markers=(
                target(
                    "河马剧场短剧广告标记",
                    text_locator("广告文本", "广告", contains=True),
                    text_locator("立即下载文本", "立即下载", contains=True, priority=21),
                    text_locator("查看详情文本", "查看详情", contains=True, priority=22),
                ),
            ),
            normal_markers=(feed_marker,),
            long_markers=(
                target(
                    "河马剧场长内容标记",
                    text_locator("全剧集文本", "全", contains=True),
                    id_locator("选集按钮ID", prefix + "episode_enter_bar", priority=11),
                ),
            ),
            interaction=InteractionSpec(),
        ),
        observation_profile=profile,
    )


def create_plugin() -> ComposedAppPlugin:
    spec = hema_theater_spec()
    navigation = NavigationController(spec)
    leave_player = spec.navigation.home_intercepts[-1]

    def go_fresh_task_page(context) -> bool:
        navigation.hard_restart_app(context)
        for _ in range(4):
            observation = context.actions.observe(
                include_ui_tree=True,
                include_screenshot=True,
            )
            if observation is not None:
                dismissed = navigation.dismiss_popup_in(
                    context,
                    spec.navigation.launch_intercepts,
                    observation,
                )
                if dismissed is not None:
                    navigation.emit_popup_dismissed(context, dismissed)
                    context.timing.operation_delay()
                    continue
            context.actions.tap_target(leave_player.close_target, timeout=0)
            context.timing.wait(1.0)
        return navigation.go_task_page(context)

    tasks = create_daily_task_set(spec, navigation=navigation)
    tasks = replace(
        tasks,
        check_in=CheckInTask(spec, go_fresh_task_page).run,
        balance=BalanceTask(spec, go_fresh_task_page).run,
        withdrawal=WithdrawalTask(spec, go_fresh_task_page).run,
        duration_reward=DurationRewardTask(spec, go_fresh_task_page).run,
    )
    return create_daily_plugin(spec, navigation=navigation, tasks=tasks)
