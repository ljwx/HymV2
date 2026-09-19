"""
悟空浏览器业务核对说明

每日流程：启动 -> 签到/刷短剧随机先后 -> 领取宝箱 -> 按概率看广告 -> 记录余额。

任务与限制：
- 新闻、小说、视频共用在线时长，当前“看剧”入口最稳定，主线使用连续短剧/视频。
- 明确广告或下载推广只短暂停留，不点赞、不进入主页。
- 宝箱和广告失败不阻断主线；签到只有出现领取弹窗或明确完成标记才记为成功。
- 任务页已达标的“待领取”计时红包会限量领取，不能把普通“今日”文案当成成功。

页面与状态标记：
- 主页面底栏包含“首页/赚钱”，“看剧”进入竖屏内容流。
- 内容流包含“观看完整漫剧/系列剧”；进入任务页前先退出沉浸流，再点底栏“赚钱”。
- 无障碍树为空是当前 App 特性，规格选用原生树，不需要修改设备驱动。
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
    DurationRewardSpec,
    InteractionSpec,
    NavigationSpec,
    PopupDismissSpec,
    VideoContentSpec,
)
from hym.apps.targets import (
    coordinate_locator,
    desc_locator,
    id_locator,
    ocr_locator,
    regex_locator,
    target,
    text_locator,
)
from hym.core.control import TaskScope
from hym.core.models import AppIdentity, Point, Rect, SystemKey, UiTreeSource
from hym.core.pages import ObservationProfile, PageSpec
from hym.runtime.context import AppContext
from hym.runtime.navigation import NavigationController
from hym.runtime.workflow import StepDefinition, StepOutcome


def wukong_browser_spec() -> AppSpec:
    package_name = "com.cat.readall"
    prefix = f"{package_name}:id/"
    profile = ObservationProfile(UiTreeSource.APPLICATION)

    home_tab = target(
        "悟空浏览器看剧入口",
        text_locator("看剧底栏文本", "看剧", region=Rect(0.10, 0.88, 0.45, 1.0)),
        ocr_locator(
            "看剧底栏OCR",
            "看剧",
            mode="exact",
            region=Rect(0.10, 0.88, 0.45, 1.0),
            confidence=0.45,
        ),
        required=True,
    )
    bottom_bar = target(
        "悟空浏览器主页面底栏",
        text_locator("首页底栏文本", "首页", region=Rect(0.0, 0.88, 0.24, 1.0)),
        text_locator("赚钱底栏标记", "赚钱", region=Rect(0.35, 0.88, 0.72, 1.0), priority=21),
        ocr_locator(
            "首页底栏OCR",
            "首页",
            mode="exact",
            region=Rect(0.0, 0.88, 0.24, 1.0),
            confidence=0.45,
        ),
        required=True,
    )
    feed_marker = target(
        "悟空浏览器短剧流标记",
        text_locator("完整漫剧文本", "观看完整漫剧", contains=True),
        text_locator("系列剧文本", "系列剧", contains=True, priority=21),
        text_locator("推荐顶部文本", "推荐", region=Rect(0.30, 0.02, 0.70, 0.16), priority=22),
        required=True,
    )
    task_entry = target(
        "悟空浏览器赚钱入口",
        text_locator("赚钱底栏文本", "赚钱", region=Rect(0.35, 0.88, 0.72, 1.0)),
        ocr_locator(
            "赚钱底栏OCR",
            "赚钱",
            mode="exact",
            region=Rect(0.35, 0.88, 0.72, 1.0),
            confidence=0.45,
        ),
        coordinate_locator("底栏赚钱入口坐标", Point(0.54, 0.96)),
        required=True,
    )
    task_marker = target(
        "悟空浏览器任务页标记",
        text_locator("今日已赚文本", "今日已赚", contains=True),
        text_locator("开宝箱文本", "开宝箱得金币", contains=True, priority=21),
        text_locator("签到文本", "签到", priority=22),
        ocr_locator("今日已赚OCR", "今日已赚", mode="contains", confidence=0.45),
        ocr_locator("日常任务OCR", "日常任务", mode="contains", confidence=0.45, priority=81),
        ocr_locator("开宝箱OCR", "开宝箱得金币", confidence=0.45, priority=82),
        required=True,
    )
    ad_close = target(
        "悟空浏览器广告关闭",
        desc_locator("广告关闭描述", "关闭"),
        text_locator("广告关闭文本", "关闭", priority=21),
        coordinate_locator("广告右上角关闭坐标", Point(0.94, 0.06)),
    )
    ad = AdSpec(
        start_markers=(
            text_target("悟空浏览器广告倒计时", "秒后可领奖励", contains=True),
            text_target("悟空浏览器激励广告", "广告", contains=True),
        ),
        completion_markers=(
            text_target("悟空浏览器广告到账", "领取成功", contains=True),
            text_target("悟空浏览器广告奖励获得", "已获得", contains=True),
        ),
        continue_targets=(),
        next_sequences=(),
        close_targets=(ad_close,),
        final_close_targets=(ad_close,),
        exit_targets=(task_marker, feed_marker),
        exit_after_wait_with_back=True,
        completion_wait_seconds=35.0,
    )
    restore_widget = PopupDismissSpec(
        marker=text_target("悟空浏览器金币挂件提示", "恢复金币挂件", contains=True),
        close_target=text_target("悟空浏览器金币挂件确认", "我知道了"),
    )

    return AppSpec(
        identity=AppIdentity("wukong_browser", package_name, "悟空浏览器", "1.0.0"),
        display_name="悟空浏览器",
        navigation=NavigationSpec(
            home_marker=bottom_bar,
            home_tab=home_tab,
            task_entry=task_entry,
            task_marker=task_marker,
            launch_intercepts=(restore_widget,),
            home_intercepts=(restore_widget,),
            reselect_home_tab=True,
            select_home_tab_before_task=False,
            home_page=PageSpec(
                "wukong_browser.main",
                package_name,
                (bottom_bar,),
                activity_patterns=(r"BrowserMainActivity$",),
                observation_profile=profile,
            ),
            task_page=PageSpec(
                "wukong_browser.task",
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
                            "悟空浏览器签到按钮",
                            text_locator("去签到文本", "去签到"),
                            text_locator("立即签到文本", "立即签到", priority=21),
                            ocr_locator("去签到OCR", "去签到", mode="exact", confidence=0.45),
                        ),
                    ),
                ),
            ),
            success_targets=(
                target(
                    "悟空浏览器签到成功",
                    text_locator("今日签到奖励文本", "今日签到领", contains=True),
                    text_locator("连续签到结果文本", "已连续签到", contains=True, priority=21),
                    text_locator("已签到文本", "已签到", contains=True),
                    text_locator("明日再来文本", "明日再来", priority=22),
                    regex_locator("连续签到天数", r"连续签到\d+天", priority=23),
                    ocr_locator(
                        "今日签到奖励OCR",
                        "今日签到领",
                        mode="contains",
                        confidence=0.45,
                    ),
                    required=True,
                ),
            ),
            close_target=target(
                "悟空浏览器签到奖励立即领取",
                text_locator("立即领取文本", "立即领取"),
                ocr_locator("立即领取OCR", "立即领取", mode="exact", confidence=0.45),
            ),
        ),
        balance=BalanceSpec(
            assets=(
                BalanceAssetSpec(
                    "coin",
                    "金币",
                    target(
                        "悟空浏览器金币余额",
                        ocr_locator(
                            "金币余额OCR",
                            r"\d+(?:\.\d+)?",
                            mode="regex",
                            region=Rect(0.04, 0.05, 0.50, 0.25),
                            confidence=0.4,
                        ),
                    ),
                    unit="金币",
                ),
            ),
        ),
        ad=ad,
        ad_entry=target(
            "悟空浏览器广告奖励入口",
            text_locator("看广告文本", "看广告", contains=True),
            ocr_locator("看广告OCR", "看广告", confidence=0.45),
        ),
        duration_reward=DurationRewardSpec(
            reward_target=target(
                "悟空浏览器宝箱奖励",
                text_locator("开宝箱文本", "开宝箱得金币", contains=True),
                ocr_locator("开宝箱OCR", "开宝箱得金币", confidence=0.45),
            ),
            success_target=target(
                "悟空浏览器宝箱到账",
                text_locator("恭喜获得文本", "恭喜获得", contains=True),
                regex_locator("宝箱冷却时间", r"\d+分\d+秒", priority=21),
                ocr_locator(
                    "宝箱冷却时间OCR",
                    r"\d+分\d+秒",
                    mode="regex",
                    region=Rect(0.70, 0.68, 1.0, 0.92),
                    confidence=0.4,
                ),
            ),
            close_target=target(
                "悟空浏览器宝箱弹窗关闭",
                coordinate_locator("宝箱弹窗底部关闭坐标", Point(0.50, 0.80)),
            ),
        ),
        content=VideoContentSpec(
            feed_marker=feed_marker,
            ad_markers=(
                text_target("悟空浏览器视频广告标记", "广告", contains=True),
                text_target("悟空浏览器视频下载标记", "立即下载", contains=True),
                text_target("悟空浏览器视频详情标记", "查看详情", contains=True),
            ),
            normal_markers=(feed_marker,),
            long_markers=(text_target("悟空浏览器长视频标记", "选集", contains=True),),
            interaction=InteractionSpec(),
        ),
        observation_profile=profile,
    )


@dataclass(frozen=True, slots=True)
class WukongPendingRewardTask:
    """领取计时奖励行中已经达标的红包，不触碰未开启任务。"""

    task_page: TaskPagePopupNavigator

    def run(self, context: AppContext) -> StepOutcome:
        pending = target(
            "悟空浏览器已达标计时红包",
            text_locator(
                "计时红包待领取文本",
                "待领取",
                region=Rect(0.03, 0.68, 0.70, 0.81),
            ),
            ocr_locator(
                "计时红包待领取OCR",
                "待领取",
                mode="exact",
                region=Rect(0.03, 0.68, 0.70, 0.81),
                confidence=0.45,
            ),
        )
        claimed = 0
        for _ in range(4):
            if not self.task_page(context):
                break
            if not context.actions.tap_target(pending, timeout=1.5):
                break
            claimed += 1
            context.timing.operation_delay()
            context.actions.press(SystemKey.BACK)
            context.timing.operation_delay()
        if claimed == 0:
            return StepOutcome.skipped("当前没有已达标的计时红包")
        return StepOutcome.success("已达标计时红包领取完成", claimed_count=claimed)


def create_plugin() -> ComposedAppPlugin:
    spec = wukong_browser_spec()
    navigation = NavigationController(spec)
    surprise = PopupDismissSpec(
        marker=target(
            "悟空浏览器惊喜奖励弹窗",
            text_locator("惊喜奖励文本", "惊喜奖励", contains=True),
            text_locator("恭喜获得文本", "恭喜获得", contains=True, priority=21),
            ocr_locator("惊喜奖励OCR", "惊喜奖励", confidence=0.45),
        ),
        close_target=target(
            "悟空浏览器惊喜奖励弹窗关闭",
            coordinate_locator("惊喜奖励底部关闭坐标", Point(0.50, 0.80)),
        ),
    )
    task_page = TaskPagePopupNavigator(
        navigation,
        (surprise,),
        max_dismissals=2,
        check_after_entry=True,
    )
    pending = WukongPendingRewardTask(task_page)
    return create_daily_plugin(
        spec,
        navigation=navigation,
        task_page_navigator=task_page,
        extra_steps=lambda _: (
            StepDefinition(
                "领取计时红包",
                "领取已达标计时红包",
                pending.run,
                recovery=navigation.recover_home,
                task_scope=TaskScope.FULL_ONLY,
            ),
        ),
    )
