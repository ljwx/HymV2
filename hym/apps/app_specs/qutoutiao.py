"""
趣头条业务核对说明

维护约定：
- 同一个 target(...) 内的 ID、文字、OCR 和结构定位是“任选一个命中”。
- 同一业务状态出现新 ID/文案时，在原 target 内追加 locator；出现新的签到页或文章类型时，
  才新增 target 或 CheckInStageSpec。保留旧标记，target_id 和策略名称不要随意改名，便于查日志。

阅读与调参：
- 本文件从上到下依次声明页面导航、首页弹窗、激励广告、签到、余额、文章浏览和专用导航恢复；
  target 和 locator 的中文名称会原样进入日志，可直接对应真机命中过程。
- 次数、概率和等待时长不写死在流程里，在 config/automation.json 的 qutoutiao.options 调整：
  content_count_* 控制文章数量，news_* 控制阅读深度和停留，*_probability 控制随机行为，
  ad_task_count_* 和 ad_* 控制广告轮数及等待，skip_content 可临时跳过内容任务。

每日流程：启动并关闭首页奖励弹窗 -> 签到/浏览文章随机先后；余额记录随机插入整轮流程，
首次失败时在收尾补一次。趣头条当前没有时段奖励，也不主动点击不稳定的独立广告任务入口。

任务与限制：
- 签到每天最多完成一次。按当前页面动态匹配“直接签到”或“立即签到”，不是固定步骤链。
- 点击签到前最多处理 3 个前置奖励广告；命中“已领 / 已连续签到N天 / 明日再来”才确认完成。
- taskcenter_sign_in_ad_rv 只是兼容旧版的被动完成信号，仅在页面不存在可点击签到分支时使用。
- 余额每天只成功记录一次，读取任务页顶部数字；失败不写当天完成状态。
- 随机打开文章，确认详情页后滚动；看到底部、点赞、查看评论都按配置概率执行，不发表评论。
- 信息流推广可能深链到其他 App；只有仍在趣头条且命中详情标记才计为文章，外部推广直接返回。
- 签到或导航途中出现的广告会播放后返回；退出失败不阻断文章流程，必要时重启应用。
- 任务页“体验领金币/看视频领金币”可能跳到浏览器下载页，不作为激励广告入口；找到稳定入口后再在本文件启用。
- 导航途中自动拉起已知广告 Activity 时，由本 App 导航策略完成一轮广告后再重试任务页。

页面与状态标记：
- 首页标签：“头条”（未选中）或“刷新”（已选中），兼容旧版“首页”；同时必须有文章列表。
- 文章列表：recycler_view，兼容旧版 bjc；文章标题：inew_text_title。
- 文章详情：avnd_text_comment 或“我来说两句”；文章底部：“相关推荐”。
- 任务页：“我的金币”/“换一批”/“N秒后自动做任务”；入口：“任务”。
- 签到遮罩：tv_sign_derect 或“直接签到”；该遮罩存在时不能把页面误判为首页。
- 首页奖励弹窗：tv_dex_title 或“看视频赚金币”；关闭：img_dismiss / “残忍离开”。
- 广告页：InciteADActivity、MobRewardVideoActivity、“奖励将于”或“打开”；退出后应重新命中任务页或首页。

待持续校准：文章流里可能混入非文章卡片，当前做法是跳过并继续；出现新签到面板时，
只需在本文件增加阶段及成功标记，不能把签到改成每天反复点击。
"""

from __future__ import annotations

from dataclasses import dataclass

from hym.apps.app_specs.common import FRAME, IMAGE, TEXT, text_target
from hym.apps.plugin import ComposedAppPlugin, create_daily_plugin
from hym.apps.specs import (
    AdSpec,
    AppSpec,
    BalanceSpec,
    CheckInSpec,
    CheckInStageSpec,
    NavigationSpec,
    NewsContentSpec,
    PopupDismissSpec,
)
from hym.apps.targets import (
    activity_locator,
    id_locator,
    layout_locator,
    ocr_locator,
    query_locator,
    regex_locator,
    target,
    text_locator,
)
from hym.core.models import AppIdentity, Rect, UiTreeSource
from hym.core.pages import ObservationProfile, PageSpec
from hym.core.targets import LocatorKind
from hym.runtime.ads import AdStateMachine
from hym.runtime.context import AppContext
from hym.runtime.navigation import NavigationController


def qutoutiao_spec() -> AppSpec:
    package_name = "com.jifen.qukan"
    prefix = "com.jifen.qukan:id/"
    observation_profile = ObservationProfile(UiTreeSource.INSTRUMENTATION)

    # 首页、任务页和文章流标记；同一 target 内可继续追加新版 ID 或文案作为备选
    home_tab = target(
        "趣头条首页标签",
        text_locator("未选中头条文本", "头条", region=Rect(0.0, 0.90, 0.25, 1.0)),
        text_locator("选中刷新文本", "刷新", region=Rect(0.0, 0.90, 0.25, 1.0), priority=21),
        text_locator("旧版首页文本", "首页", priority=22),
        layout_locator("旧版首页结构", FRAME, position=(0.1, 0.953), size=(0.2, 0.0546)),
        required=True,
    )
    task_marker = target(
        "趣头条任务页标记",
        text_locator("旧版任务标记", "换一批"),
        text_locator("当前任务标记", "我的金币", priority=21),
        regex_locator("自动任务倒计时", r"\d+s后自动做任务", priority=22),
        required=True,
    )
    news_list_marker = target(
        "趣头条信息流列表",
        id_locator("信息流列表ID", prefix + "recycler_view"),
        id_locator("旧版信息流列表ID", prefix + "bjc", priority=11),
        required=True,
    )
    sign_overlay = target(
        "趣头条签到遮罩",
        id_locator("直接签到ID", prefix + "tv_sign_derect"),
        text_locator("直接签到文本", "直接签到"),
        text_locator("旧版直接签到文本", "直接签到，不提现", priority=21),
    )
    home_reward_popup = PopupDismissSpec(
        marker=target(
            "趣头条首页奖励弹窗",
            id_locator("奖励弹窗标题ID", prefix + "tv_dex_title"),
            text_locator("奖励弹窗标题文本", "看视频赚金币", contains=True),
        ),
        close_target=target(
            "趣头条首页弹窗关闭",
            id_locator("奖励弹窗关闭ID", prefix + "img_dismiss"),
            text_locator("残忍离开文本", "残忍离开", priority=21),
            layout_locator(
                "旧版首页关闭结构",
                IMAGE,
                position=(0.4991, 0.7419),
                size=(0.0975, 0.0438),
            ),
        ),
    )

    # 激励广告允许多种入口状态，退出时必须回到任务页或首页
    ad_close = target(
        "趣头条广告关闭",
        layout_locator("广告关闭结构", IMAGE, position=(0.9108, 0.0696), size=(0.0433, 0.0194)),
    )
    ad = AdSpec(
        start_markers=(
            target(
                "趣头条激励广告页面",
                activity_locator(
                    "趣头条 Incite 广告Activity",
                    r"InciteADActivity$",
                    package_name=package_name,
                ),
                activity_locator(
                    "趣头条百度广告Activity",
                    r"MobRewardVideoActivity$",
                    package_name=package_name,
                    priority=6,
                ),
            ),
            text_target("趣头条奖励倒计时", "奖励将于", contains=True),
            text_target("趣头条打开广告", "打开"),
        ),
        continue_targets=(text_target("趣头条放弃福利", "放弃福利"),),
        next_sequences=(),
        close_targets=(ad_close,),
        final_close_targets=(ad_close,),
        exit_targets=(task_marker, home_tab),
        completion_wait_seconds=33.0,
        exit_after_wait_with_back=True,
    )

    return AppSpec(
        identity=AppIdentity("qutoutiao", package_name, "趣头条", "1.0.0"),
        display_name="趣头条",
        navigation=NavigationSpec(
            home_marker=home_tab,
            home_tab=home_tab,
            task_entry=text_target("趣头条任务入口", "任务", required=True),
            task_marker=task_marker,
            launch_intercepts=(home_reward_popup,),
            home_intercepts=(home_reward_popup,),
            task_dismiss=(),
            home_attempts=8,
            home_page=PageSpec(
                "qutoutiao.home",
                package_name,
                (home_tab, news_list_marker),
                forbidden_markers=(task_marker, sign_overlay),
                activity_patterns=(r"MainActivity$",),
                minimum_markers=2,
                observation_profile=observation_profile,
            ),
            task_page=PageSpec(
                "qutoutiao.task",
                package_name,
                (task_marker, sign_overlay),
                activity_patterns=(r"MainActivity$",),
                minimum_markers=1,
                observation_profile=observation_profile,
            ),
        ),

        # 每天一次；新签到页面新增 stage，同一按钮换 ID 则在原 target 中追加 locator
        # 根据本次页面实际命中的分支推进，不假定签到界面固定
        check_in=CheckInSpec(
            stages=(
                CheckInStageSpec(
                    "直接签到",
                    (
                        target(
                            "趣头条直接签到",
                            id_locator("直接签到按钮ID", prefix + "tv_sign_derect"),
                            text_locator("直接签到按钮文本", "直接签到"),
                            text_locator("旧版直接签到按钮文本", "直接签到，不提现", priority=21),
                        ),
                    ),
                ),
                CheckInStageSpec(
                    "普通签到",
                    (text_target("趣头条立即签到", "立即签到"),),
                ),
            ),
            success_targets=(
                target(
                    "趣头条签到成功",
                    text_locator("已领取文本", "已领"),
                    regex_locator("已签到天数", r"已连续签到[1-9]\d*天", priority=21),
                    text_locator("明日签到文本", "明日再来", priority=22),
                    required=True,
                ),
            ),
            passive_success_targets=(
                target(
                    "趣头条签到区域",
                    id_locator("签到区域ID", prefix + "taskcenter_sign_in_ad_rv"),
                ),
            ),
            pre_ad_attempts=3,
        ),

        # 余额成功后写入当天状态，后续随机节点和收尾节点都会自动跳过
        balance=BalanceSpec(
            balance_target=target(
                "趣头条余额",
                regex_locator("余额文本", r"\d+(?:\.\d+)?", region=Rect(0.12, 0.04, 0.40, 0.14)),
                layout_locator("余额结构", TEXT, position=(0.2616, 0.0876), size=(0.1491, 0.0183)),
                ocr_locator("余额OCR", r"\d+(?:\.\d+)?", mode="regex", region=Rect(0.12, 0.04, 0.40, 0.14)),
                required=True,
            )
        ),
        ad=ad,
        duration_reward=None,

        # 新文章卡片 ID 追加到 feed_item；新详情特征追加到 detail_marker
        # 随机选文章；只有命中详情标记才计为完成一次浏览
        content=NewsContentSpec(
            feed_item=target(
                "趣头条随机文章",
                query_locator(
                    "当前文章标题ID",
                    priority=10,
                    options={
                        "resource_id": prefix + "inew_text_title",
                        "pick": "random",
                    },
                ),
                query_locator(
                    "当前文章标题",
                    options={
                        "resource_id": prefix + "inew_text_title",
                        "ancestor_resource_id": prefix + "recycler_view",
                        "pick": "random",
                    },
                ),
                query_locator(
                    "旧版文章列表子项",
                    priority=61,
                    options={
                        "parent_resource_id": prefix + "bjc",
                        "clickable": True,
                        "pick": "random",
                    },
                ),
                required=True,
            ),
            detail_marker=target(
                "趣头条文章详情",
                id_locator("当前评论入口ID", prefix + "avnd_text_comment"),
                text_locator("评论入口文本", "我来说两句", contains=True, priority=21),
                required=True,
            ),
            like_target=text_target("趣头条文章点赞", "点赞", contains=True),
            comment_target=text_target("趣头条浏览评论", "全部评论", contains=True),
            bottom_marker=text_target("趣头条文章底部", "相关推荐", contains=True),
        ),
        observation_profile=observation_profile,
    )


@dataclass(frozen=True, slots=True)
class QutoutiaoTaskPageNavigator:
    """在趣头条进入任务页时接管已知奖励广告。"""

    spec: AppSpec
    navigation: NavigationController

    def __call__(self, context: AppContext) -> bool:
        recovered_ad = False
        for attempt in range(2):
            if not recovered_ad and self._recover_ad(context):
                recovered_ad = True
            if self.navigation.go_task_page(context):
                return True
            if not recovered_ad and self._recover_ad(context):
                recovered_ad = True
                continue
            if attempt == 0:
                context.timing.operation_delay()
        return False

    def _recover_ad(self, context: AppContext) -> bool:
        ad = self.spec.ad
        if ad is None:
            return False
        observation = context.actions.observe(
            include_ui_tree=False,
            include_screenshot=False,
        )
        if observation is None:
            return False
        for target_spec in ad.start_markers:
            if not all(locator.kind is LocatorKind.ACTIVITY for locator in target_spec.locators):
                continue
            if not context.actions.resolve_in(target_spec, observation).found:
                continue
            context.emit(
                "navigation.blocking_ad.detected",
                "导航广告接管",
                "检测到导航途中遗留的奖励广告，完成后再进入任务页",
                workflow_id="daily",
                status="recovering",
                data={"activity_name": observation.activity.activity_name},
            )
            AdStateMachine().run(context, ad)
            return True
        return False


def create_plugin() -> ComposedAppPlugin:
    """趣头条组合新闻任务与专用任务页导航。"""

    spec = qutoutiao_spec()
    navigation = NavigationController(spec)
    return create_daily_plugin(
        spec,
        navigation=navigation,
        task_page_navigator=QutoutiaoTaskPageNavigator(spec, navigation),
    )
