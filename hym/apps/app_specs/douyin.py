"""
抖音极速版业务核对说明

维护约定：
- 同一个 target(...) 内的 ID、文字、描述、OCR、图片和结构定位是“任选一个命中”。
- 同一业务状态出现新 ID/文案时，在原 target 内追加 locator；出现新的页面状态或流程分支时，
  才新增 target 或 CheckInStageSpec。保留旧标记，target_id 和策略名称不要随意改名，便于查日志。

每日流程：启动应用 -> 签到/刷视频随机先后 -> 领取时段奖励 -> 按概率执行广告任务；
余额在这些步骤中随机插入，首次没记录成功时会在收尾补一次。

任务与限制：
- 签到每天最多完成一次，并按当前页面动态匹配新版面板、旧版进度条或确认领取页。
- “去签到”和旧版“进度条”只负责打开下一层，不算领取；“主动签到/立即签到领”才是提交动作。
- 命中“已签到N天”或“打开签到提醒按钮”才确认完成。提交后状态不明时当天不重复领取。
- 余额每天只成功记录一次。当前节点只适合截图留证，尚未稳定解析出余额文字。
- 时段奖励匹配“开宝箱得金币”，以“开宝箱奖励已到账”为成功标记，可继续看奖励广告。
- 刷视频时先分类广告、长视频和普通视频；明确广告只短暂停留且禁止互动。
- 当前普通视频标记覆盖不足，未分类内容按保守时长浏览且不互动，不直接当成疑似广告。
- 普通视频约 8% 快速划过、25% 尝试完整观看，其余按常规时长观看；所有比例和时长可独立配置。
- 普通/长视频可按配置概率关注、点赞、查看评论、进入作者主页并浏览随机作品。
- 明确广告仍快速划走；后续只有找到可靠的新广告信号，才补进广告标记组。

页面与状态标记：
- 首页：root_view + user_avatar/viewpager，且不能出现任务页标记；首页标签：“首页”。
- 任务入口：描述“福袋”，兼容图片和底栏结构；任务页：“每天都能领金币”/
  “已签到N天”/标题“赚钱任务”。
- 视频广告：“当前直播间可用”/“广告”/“查看详情”/“立即下载”。
- 普通视频：“全屏观看”或“拍同款”；长视频：“点击进入看全集”/“听抖音”/“合集”。
- 激励广告：“N秒后可领奖励”；连续广告按“领取成功，关闭”后再匹配“下一个广告”。

待持续校准：页面结构和文案变化时优先在对应标记组增加新分支；不能因为某一次页面成立，
就删除仍可能出现的旧版签到和广告分支。
"""

from __future__ import annotations

from hym.apps.app_specs.common import FRAME, GROUP, IMAGE, RECYCLER, text_target
from hym.apps.plugin import ConfiguredAppPlugin
from hym.apps.specs import (
    AdSpec,
    AppSpec,
    BalanceSpec,
    CheckInSpec,
    CheckInStageSpec,
    DurationRewardSpec,
    InteractionSpec,
    NavigationSpec,
    VideoContentSpec,
)
from hym.apps.targets import (
    desc_locator,
    id_locator,
    image_locator,
    layout_locator,
    ocr_locator,
    query_locator,
    regex_locator,
    target,
    text_locator,
)
from hym.core.models import AppIdentity, Rect, UiTreeSource
from hym.core.pages import ObservationProfile, PageSpec


def douyin_spec() -> AppSpec:
    package_name = "com.ss.android.ugc.aweme.lite"
    prefix = "com.ss.android.ugc.aweme.lite:id/"
    observation_profile = ObservationProfile(UiTreeSource.INSTRUMENTATION)

    # 首页、任务页和视频流标记；同一 target 内可继续追加新版 ID 或文案作为备选
    home_marker = target("抖音首页标记", id_locator("首页根节点", prefix + "root_view"), required=True)
    home_tab = text_target("抖音首页标签", "首页", required=True)
    task_entry = target(
        "抖音任务入口",
        desc_locator("福袋描述", "福袋"),
        image_locator("任务标签图片", "douyin/main_task_tab.png"),
        layout_locator("福袋结构", FRAME, position=(0.5, 0.9438), size=(0.2033, 0.0730)),
        required=True,
    )
    task_marker = target(
        "抖音任务页标记",
        desc_locator("每日金币描述", "每天都能领金币"),
        regex_locator("已签到描述", r"已签到[1-9]\d*天", priority=21),
        ocr_locator(
            "赚钱任务标题OCR",
            "赚钱任务",
            mode="exact",
            region=Rect(0.25, 0.04, 0.75, 0.13),
            confidence=0.7,
        ),
        required=True,
    )
    feed_marker = target(
        "抖音内容标记",
        id_locator("用户头像ID", prefix + "user_avatar"),
        id_locator("视频容器ID", prefix + "viewpager", priority=11),
        required=True,
    )

    # 激励广告可能连续出现，依次处理关闭提示和“下一个广告”入口
    close_ad = target("抖音广告关闭", desc_locator("关闭描述", "领取成功，关闭，按钮"))
    ad = AdSpec(
        start_markers=(
            target(
                "抖音广告倒计时",
                text_locator("倒计时文本", "秒后可领奖励", contains=True),
                ocr_locator("倒计时OCR", "秒后可领奖励"),
            ),
        ),
        completion_markers=(close_ad,),
        continue_targets=(target("抖音广告返回", id_locator("广告返回ID", prefix + "iv_back")),),
        next_sequences=((
            close_ad,
            target(
                "抖音下一个广告",
                desc_locator("下一个广告描述", "下一个广告"),
                layout_locator("下一个广告结构", GROUP, position=(0.5, 0.4632), size=(0.7583, 0.3928)),
            ),
        ),),
        close_targets=(close_ad,),
        final_close_targets=(close_ad,),
        exit_targets=(task_marker, home_marker),
    )

    return AppSpec(
        identity=AppIdentity("douyin", package_name, "抖音极速版", "1.0.0"),
        display_name="抖音极速版",
        navigation=NavigationSpec(
            home_marker,
            home_tab,
            task_entry,
            task_marker,
            home_page=PageSpec(
                "douyin.home",
                package_name,
                (home_marker, feed_marker),
                forbidden_markers=(task_marker,),
                activity_patterns=(r"SplashActivity$",),
                minimum_markers=2,
                observation_profile=observation_profile,
            ),
            task_page=PageSpec(
                "douyin.task",
                package_name,
                (task_marker,),
                activity_patterns=(r"SplashActivity$",),
                observation_profile=observation_profile,
            ),
        ),

        # 每天一次；新页面层级新增 stage，同一按钮换 ID 则在原 target 中追加 locator
        # 中间阶段只负责导航，确认领取阶段才写入待确认检查点
        check_in=CheckInSpec(
            stages=(
                CheckInStageSpec(
                    "打开签到面板",
                    (
                        target(
                            "抖音去签到",
                            text_locator("去签到文本", "去签到"),
                            ocr_locator(
                                "去签到OCR",
                                "去签到",
                                mode="exact",
                                region=Rect(0.70, 0.50, 0.98, 0.75),
                                confidence=0.25,
                            ),
                        ),
                    ),
                    commit_action=False,
                ),
                CheckInStageSpec(
                    "打开旧版签到进度",
                    (
                        target(
                            "抖音签到进度",
                            desc_locator("进度条动作描述", "进度条"),
                            layout_locator(
                                "进度条结构",
                                GROUP,
                                position=(0.5, 0.4307),
                                size=(0.675, 0.0097),
                            ),
                        ),
                    ),
                    state_markers=(target("抖音旧版进度状态", desc_locator("进度条描述", "进度条")),),
                    commit_action=False,
                ),
                CheckInStageSpec(
                    "确认领取签到奖励",
                    (
                        target(
                            "抖音确认签到",
                            desc_locator("主动签到描述", "主动签到"),
                            ocr_locator(
                                "立即签到OCR",
                                "立即签到领",
                                mode="contains",
                                region=Rect(0.15, 0.75, 0.90, 0.95),
                                confidence=0.65,
                            ),
                        ),
                    ),
                ),
            ),
            success_targets=(
                target(
                    "抖音签到成功",
                    regex_locator("已签到天数", r"已签到[1-9]\d*天"),
                    desc_locator("旧版签到提醒描述", "打开签到提醒按钮", priority=21),
                    required=True,
                ),
            ),
            close_with_back=True,
            max_transitions=4,
        ),

        # 该区域目前无法稳定提取文字，因此每天保存一次页面截图作为余额证据
        balance=BalanceSpec(
            balance_target=target(
                "抖音余额区域",
                layout_locator("余额区域结构", GROUP, position=(0.5, 0.1794), size=(0.915, 0.1389)),
                required=True,
            ),
            screenshot_only=True,
        ),
        ad=ad,
        duration_reward=DurationRewardSpec(
            reward_target=target(
                "抖音时段奖励",
                desc_locator("开宝箱描述", "开宝箱得金币"),
            ),
            success_target=text_target("抖音奖励到账", "开宝箱奖励已到账"),
            ad_target=target(
                "抖音奖励广告",
                image_locator("奖励广告图片", "douyin/go_video_ad_icon.png"),
                layout_locator("奖励广告结构", GROUP, position=(0.5, 0.5535), size=(0.5866, 0.0625)),
            ),
            close_target=target(
                "抖音奖励关闭",
                image_locator("奖励关闭图片", "douyin/duration_reward_close_icon.png"),
                layout_locator("奖励关闭结构", IMAGE, position=(0.8041, 0.3164), size=(0.075, 0.0333)),
            ),
        ),

        # 新广告特征追加到 ad_markers，不能混入 normal_markers
        # 内容分类优先级为广告、长视频、普通视频；未分类内容默认不互动
        content=VideoContentSpec(
            feed_marker=feed_marker,
            ad_markers=(
                target("抖音直播广告", desc_locator("直播广告描述", "当前直播间可用")),
                text_target("抖音广告文本", "广告"),
                target("抖音详情广告", desc_locator("查看详情描述", "查看详情")),
                target("抖音下载广告", desc_locator("立即下载描述", "立即下载")),
            ),
            normal_markers=tuple(
                text_target(f"抖音常规内容-{text}", text)
                for text in ("全屏观看", "拍同款")
            ),
            long_markers=tuple(
                text_target(f"抖音长内容-{text}", text)
                for text in ("点击进入看全集", "听抖音", "合集")
            ),
            interaction=InteractionSpec(
                like_target=target(
                    "抖音点赞",
                    layout_locator(
                        "点赞结构",
                        IMAGE,
                        position=(0.9141, 0.5438),
                        size=(0.0975, 0.043),
                    ),
                ),
                comment_target=target(
                    "抖音评论",
                    layout_locator(
                        "评论结构",
                        IMAGE,
                        position=(0.9141, 0.6277),
                        size=(0.0975, 0.0438),
                    ),
                ),
                profile_target=target("抖音作者主页", id_locator("用户头像ID", prefix + "user_avatar")),
                profile_marker=text_target("抖音作品页标记", "获赞"),
                work_item_target=target(
                    "抖音随机作品",
                    query_locator(
                        "作品列表子项",
                        options={"parent_class": RECYCLER, "clickable": True, "pick": "random"},
                    ),
                ),
                follow_target=target(
                    "抖音关注",
                    layout_locator(
                        "关注结构",
                        IMAGE,
                        position=(0.9216, 0.4910),
                        size=(0.065, 0.0292),
                    ),
                ),
            ),
        ),
        ad_entry=target(
            "抖音广告任务入口",
            desc_locator("广告任务描述", "分钟完成一次"),
            text_locator("广告任务文本", "分钟完成一次", contains=True),
            ocr_locator("广告任务OCR", "分钟完成一次"),
        ),
        observation_profile=observation_profile,
    )


def create_plugin() -> ConfiguredAppPlugin:
    """抖音插件入口；需要独有任务时在本文件替换为专用插件子类。"""

    return ConfiguredAppPlugin(douyin_spec())
