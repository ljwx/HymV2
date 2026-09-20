"""
快手极速版业务核对说明

维护约定：
- 同一个 target(...) 内的 ID、文字、描述、OCR、图片和结构定位是“任选一个命中”。
- 同一业务状态出现新 ID/文案时，在原 target 内追加 locator；出现新的页面状态或流程分支时，
  才新增 target 或 CheckInStageSpec。保留旧标记，target_id 和策略名称不要随意改名，便于查日志。

阅读与调参：
- 本文件从上到下依次声明页面导航、激励广告、签到、余额、提现信息、时段奖励、视频分类与互动；
  target 和 locator 的中文名称会原样进入日志，可直接对应真机命中过程。
- 次数、概率和等待时长不写死在流程里，在 config/automation.json 的 kuaishou.options 调整：
  content_count_* 控制刷视频数量，*_duration_* 控制各类视频时长，*_probability 控制随机行为，
  ad_task_count_* 和 ad_* 控制广告轮数及等待，skip_content 可临时跳过内容任务。

每日流程：启动并处理弹窗 -> 签到/刷视频随机先后 -> 领取时段奖励 -> 按概率执行广告任务；
余额在这些步骤中随机插入，首次没记录成功时会在收尾补一次；最后只读更新提现门槛。

任务与限制：
- 签到每天最多完成一次。当前可执行入口是“立即签到”，成功标记为“查看日历”/
  “已签到N/N天”/“N金币待领取，继续看视频得金币”/旧版“明日签到可领”。提交后状态不明时当天不重复点击。
- “连续打卡白拿手机/去领取”属于另一种 365 天活动，当前不能当成每日签到入口。
- 签到完成后如果出现“去看视频”，可继续处理奖励广告，然后关闭任务弹窗。
- 余额从任务页顶部识别金币和现金；两个字段都命中后每天记录一次，失败时不写完成状态。
- 时段奖励匹配“金币立即领取”、“点击领N金币”或任务页右下角“点可领N金币”，到账后可继续看奖励广告。
- 刷视频时先分类广告、长视频和普通视频；明确广告只短暂停留且禁止互动。
- 视频流结构存在但关键分类标记均未命中时，按可配置的疑似广告快速划走并记录原因。
- 普通视频约 8% 快速划过、25% 尝试完整观看，其余按常规时长观看；分类结束后仍保留最低停留时间。
- 当前进度条节点不暴露进度和总时长，“完整观看尝试”使用较长等待兜底，日志不会误记成确认看完。
- 普通/长视频可按配置概率关注、点赞、查看评论、进入作者主页并浏览随机作品。
- 未开启疑似广告策略的 App 才按未分类视频保守浏览，默认不互动。

页面与状态标记：
- 首页：同时命中 bottom_bar_container 和“首页”；任务入口：“去赚钱”，树为空时用底部 OCR 兜底；任务页：“任务中心”。
- 启动关闭：close_btn；邀请弹窗：“邀请2个新用户必得”；返回拦截：“离开”。
- 视频流：follow_avatar_view，兼容直播预览 layout_root_hot_live_play。
- 广告视频：ad_download_progress / slide_play_right_link_icon / ad_card_container_root /
  slide_play_ad_info_layout / 直播卖货文案 / 推广关键词。
- 普通视频：“全屏观看”/演绎声明/作品文案等；长视频：“继续观看完整版”/“完整版”/“合集”。
- 激励广告：AwardVideoPlayActivity、video_countdown 或直播底部遮罩。完整播放后按返回触发奖励弹窗；弹窗明确支持
  “领取奖励”时按配置随机追加 0~2 轮，达到上限后点右上角关闭，最终回到任务页或首页。

待持续校准：广告标记按真实页面持续追加，不能用单一 ID 判断所有广告；当前代码没有执行
“广告视频低概率进入广告主页”，因为点击目标和安全退出路径还没有稳定标记，需实测后再补。
"""

from __future__ import annotations

from hym.apps.app_specs.common import IMAGE, text_target
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
    WithdrawalSpec,
)
from hym.apps.targets import (
    activity_locator,
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


def kuaishou_spec() -> AppSpec:
    package_name = "com.kuaishou.nebula"
    prefix = "com.kuaishou.nebula:id/"
    ad_prefix = "com.kuaishou.nebula.commercial_neo:id/"
    # 当前版本只能从应用界面树稳定读取首页和任务页。
    tree_source = UiTreeSource.APPLICATION
    observation_profile = ObservationProfile(UiTreeSource.APPLICATION)

    # 首页和任务页标记；同一 target 内可继续追加新版 ID 或文案作为备选
    home_marker = target(
        "快手首页标记",
        id_locator("首页底栏", prefix + "bottom_bar_container"),
        required=True,
        metadata={"ui_tree_source": tree_source},
    )
    home_tab = target(
        "快手首页标签",
        text_locator("首页底部文本", "首页", region=Rect(0.0, 0.90, 0.25, 1.0)),
        desc_locator("首页底部描述", "首页"),
        required=True,
        metadata={"ui_tree_source": tree_source},
    )
    task_marker = text_target(
        "快手任务页标记",
        "任务中心",
        required=True,
        ui_tree_source=tree_source,
    )
    task_close = target(
        "快手任务弹窗关闭",
        image_locator("任务页关闭图片", "kuaishou/task_tab_page_close_icon.png"),
        layout_locator("任务页关闭结构", IMAGE, position=(0.92, 0.1921), size=(0.0708, 0.0314)),
        metadata={"ui_tree_source": tree_source},
    )
    # 每轮奖励到账后按返回；只在奖励挽留弹窗内随机续看，达到上限后点右上角关闭
    ad_exit_targets = (task_marker, home_marker)
    ad_exit_prompt = target(
        "快手广告退出弹窗",
        text_locator("继续观看按钮文本", "继续观看"),
        text_locator("换广告按钮文本", "换一个广告", priority=21),
        regex_locator("追加奖励标题", r"再看\s*1\s*个", priority=22),
    )
    ad_exit_prompt_close = target(
        "快手广告退出弹窗关闭",
        desc_locator("退出弹窗关闭描述", "close_view"),
        layout_locator(
            "退出弹窗关闭结构",
            IMAGE,
            position=(0.805, 0.38),
            size=(0.05, 0.022),
            position_tolerance=0.08,
            size_tolerance=0.6,
            priority=65,
        ),
    )
    ad_completion = target(
        "快手广告奖励完成",
        id_locator("倒计时结束ID", ad_prefix + "video_countdown_end_icon"),
        regex_locator("广告奖励到账文本", r"已成功领取\s*\d+\s*金币", priority=20),
    )
    ad = AdSpec(
        start_markers=(
            target(
                "快手激励广告页面",
                activity_locator(
                    "激励广告Activity",
                    r"AwardVideoPlayActivity$",
                    package_name=package_name,
                ),
            ),
            target("快手广告倒计时", id_locator("广告倒计时ID", ad_prefix + "video_countdown")),
            target(
                "快手直播广告",
                id_locator(
                    "直播广告ID",
                    "com.kuaishou.nebula.live_audience_plugin:id/live_audience_bottom_mask_view",
                ),
            ),
        ),
        completion_markers=(ad_completion,),
        continue_targets=(),
        next_sequences=(),
        close_targets=(ad_exit_prompt_close,),
        final_close_targets=(
            target(
                "快手直播关闭",
                id_locator(
                    "直播关闭ID",
                    "com.kuaishou.nebula.live_audience_plugin:id/live_close_place_holder",
                ),
            ),
            target("快手最终关闭", desc_locator("最终描述关闭", "close_view")),
        ),
        exit_targets=ad_exit_targets,
        exit_after_wait_with_back=True,
        exit_prompt_markers=(ad_exit_prompt,),
        exit_prompt_continue_targets=(text_target("快手追加广告奖励", "领取奖励"),),
        exit_prompt_close_targets=(ad_exit_prompt_close,),
        extra_rounds_min=0,
        extra_rounds_max=2,
    )

    return AppSpec(
        identity=AppIdentity("kuaishou", package_name, "快手极速版", "1.0.0"),
        display_name="快手极速版",
        navigation=NavigationSpec(
            home_marker=home_marker,
            home_tab=home_tab,
            task_entry=target(
                "快手任务入口",
                text_locator("任务底部文本", "去赚钱", region=Rect(0.55, 0.90, 0.85, 1.0)),
                desc_locator("任务底部描述", "去赚钱"),
                ocr_locator(
                    "任务底部OCR",
                    "去赚钱",
                    mode="exact",
                    region=Rect(0.55, 0.90, 0.85, 1.0),
                    confidence=0.45,
                    priority=20,
                ),
                required=True,
                metadata={"ui_tree_source": tree_source},
            ),
            task_marker=task_marker,
            launch_dismiss=(
                target(
                    "快手启动关闭",
                    id_locator("启动关闭ID", prefix + "close_btn"),
                    metadata={"ui_tree_source": tree_source},
                ),
            ),
            launch_intercepts=(
                PopupDismissSpec(
                    marker=text_target(
                        "快手邀请活动弹窗",
                        "邀请2个新用户必得",
                        ui_tree_source=tree_source,
                    ),
                    close_target=target(
                        "快手邀请活动关闭",
                        layout_locator(
                            "邀请活动关闭结构",
                            IMAGE,
                            position=(0.5, 0.7003),
                            size=(0.0758, 0.0340),
                        ),
                        metadata={"ui_tree_source": tree_source},
                    ),
                ),
            ),
            home_intercepts=(
                PopupDismissSpec(
                    close_target=text_target(
                        "快手确认离开",
                        "离开",
                        ui_tree_source=tree_source,
                    )
                ),
            ),
            task_dismiss=(task_close,),
            home_page=PageSpec(
                "kuaishou.home",
                package_name,
                # 作者主页也会保留底栏容器，必须同时看到“首页”标签才算首页。
                (home_marker, home_tab),
                forbidden_markers=(task_marker,),
                activity_patterns=(r"HomeActivity$",),
                minimum_markers=2,
                observation_profile=observation_profile,
            ),
            task_page=PageSpec(
                "kuaishou.task",
                package_name,
                (task_marker,),
                activity_patterns=(r"HomeActivity$",),
                observation_profile=observation_profile,
            ),
        ),

        # 每天一次；新入口新增 stage，同一入口换 ID 则在原 target 中追加 locator
        # 365 天打卡活动没有列入这里，避免误当作每日签到
        check_in=CheckInSpec(
            stages=(
                CheckInStageSpec(
                    "领取签到奖励",
                    (
                        target(
                            "快手立即签到",
                            text_locator("签到按钮文本", "立即签到"),
                            ocr_locator(
                                "签到按钮OCR",
                                "立即签到",
                                mode="exact",
                                region=Rect(0.5, 0.10, 1.0, 0.75),
                                confidence=0.65,
                            ),
                            image_locator("旧版签到图片", "kuaishou/check_in_icon.png", priority=90),
                            metadata={"ui_tree_source": tree_source},
                        ),
                    ),
                    wait_seconds=5.0,
                ),
            ),
            success_targets=(
                target(
                    "快手签到成功",
                    text_locator("签到日历按钮", "查看日历"),
                    regex_locator("签到完成天数", r"已签到[1-9]\d*/\d+天", priority=21),
                    regex_locator(
                        "连续看视频签到完成",
                        r"\d+金币待领取，继续看视频得金币",
                        priority=22,
                        region=Rect(0.05, 0.25, 0.95, 0.60),
                    ),
                    text_locator("旧版签到状态", "明日签到可领", priority=23),
                    required=True,
                    metadata={"ui_tree_source": tree_source},
                ),
            ),
            post_ad_target=text_target(
                "快手签到后广告",
                "去看视频",
                ui_tree_source=tree_source,
            ),
            close_target=task_close,
        ),

        # 任务页顶部左右分别是金币和现金，两个字段都命中后才写入当天状态。
        balance=BalanceSpec(
            assets=(
                BalanceAssetSpec(
                    "coin",
                    "金币",
                    target(
                        "快手金币余额",
                        ocr_locator(
                            "顶部金币数字OCR",
                            r"\d[\d,]*",
                            mode="regex",
                            region=Rect(0.05, 0.17, 0.35, 0.23),
                            confidence=0.45,
                        ),
                        metadata={"ui_tree_source": tree_source},
                    ),
                    unit="金币",
                ),
                BalanceAssetSpec(
                    "cash",
                    "现金",
                    target(
                        "快手现金余额",
                        ocr_locator(
                            "顶部现金数字OCR",
                            r"\d+(?:\.\d+)?",
                            mode="regex",
                            region=Rect(0.52, 0.17, 0.82, 0.23),
                            confidence=0.30,
                        ),
                        metadata={"ui_tree_source": tree_source},
                    ),
                    scale=2,
                    unit="元",
                ),
            ),
        ),
        withdrawal=WithdrawalSpec(
            entry_sequence=(
                target(
                    "快手提现入口",
                    text_locator("领现金按钮文本", "领现金"),
                    ocr_locator(
                        "领现金按钮OCR",
                        "领现金",
                        mode="exact",
                        region=Rect(0.65, 0.12, 1.0, 0.30),
                        confidence=0.45,
                    ),
                ),
            ),
            available_region=Rect(0.05, 0.13, 0.45, 0.28),
            minimum_region=Rect(0.05, 0.39, 0.95, 0.58),
            details_region=Rect(0.03, 0.34, 0.97, 0.88),
        ),
        ad=ad,
        # 任务页右下角宝箱领取后原位变成倒计时，不会稳定出现到账弹窗。
        # 这里只认右下角入口和冷却状态，避免用布局兜底误点任务列表。
        duration_reward=DurationRewardSpec(
            reward_target=target(
                "快手任务页右下角宝箱",
                regex_locator(
                    "右下角宝箱可领取描述",
                    r"点可领\s*\d+金币",
                    region=Rect(0.70, 0.70, 1.0, 1.0),
                ),
                metadata={"ui_tree_source": tree_source},
            ),
            success_target=target(
                "快手宝箱进入冷却",
                regex_locator(
                    "右下角宝箱倒计时结构",
                    r"\d{2}:\d{2}\s*\d+金币",
                    region=Rect(0.70, 0.70, 1.0, 1.0),
                ),
                ocr_locator(
                    "右下角宝箱倒计时OCR",
                    r"\d{2}:\d{2}\s*\d+金币",
                    mode="regex",
                    region=Rect(0.70, 0.70, 1.0, 1.0),
                    confidence=0.45,
                    priority=20,
                ),
                metadata={"ui_tree_source": tree_source},
            ),
            result_wait_seconds=3.0,
        ),

        # 新广告特征追加到 ad_markers，不能混入 normal_markers
        # 广告标记优先于长视频和普通视频；只有非广告分类才允许概率互动
        content=VideoContentSpec(
            feed_marker=target(
                "快手内容标记",
                id_locator("头像ID", prefix + "follow_avatar_view"),
                id_locator("直播预览ID", prefix + "layout_root_hot_live_play", priority=11),
                required=True,
            ),
            ad_markers=(
                target("快手购物广告", id_locator("下载进度ID", prefix + "ad_download_progress")),
                text_target("快手咨询广告", "咨询"),
                target("快手侧边广告", id_locator("侧边广告ID", prefix + "slide_play_right_link_icon")),
                target("快手广告卡片", id_locator("广告卡片ID", prefix + "ad_card_container_root")),
                target("快手广告信息", id_locator("广告信息ID", prefix + "slide_play_ad_info_layout")),
                target(
                    "快手直播卖货",
                    id_locator("直播预览根节点", prefix + "layout_root_hot_live_play"),
                    text_locator("直播卖货文本", "直播卖货", priority=21),
                    text_locator("直播入口文本", "点击进入直播间", priority=22),
                ),
                target(
                    "快手推广文案",
                    ocr_locator(
                        "推广关键词OCR",
                        r"私信|下单|购买|咨询|预约|到店|门店|加微信|领券|立即抢购|免费领取",
                        mode="regex",
                        region=Rect(0.0, 0.10, 0.85, 0.93),
                        confidence=0.6,
                    ),
                ),
            ),
            normal_markers=(
                text_target("快手全屏内容", "全屏观看"),
                text_target("快手演绎声明", "作者声明：演绎情节，仅供娱乐"),
                target("快手作品文案", id_locator("作品文案ID", prefix + "element_caption_label")),
                target("快手常规入口", id_locator("常规入口ID", prefix + "general_entry_single_root_view")),
                target("快手图文内容", id_locator("图文ID", prefix + "pic_text")),
                target("快手日期内容", id_locator("日期ID", prefix + "create_date_tv")),
            ),
            long_markers=tuple(
                text_target(f"快手长内容-{text}", text)
                for text in ("继续观看完整版", "完整版", "合集")
            ),
            interaction=InteractionSpec(
                like_target=target("快手点赞", id_locator("点赞ID", prefix + "like_icon")),
                comment_target=target("快手评论", id_locator("评论ID", prefix + "comment_icon")),
                profile_target=target("快手作者主页", id_locator("用户名ID", prefix + "user_name_text_view")),
                profile_marker=target(
                    "快手作品页标记",
                    id_locator("快手号ID", prefix + "profile_user_kwai_id"),
                ),
                work_item_target=target(
                    "快手随机作品",
                    query_locator(
                        "作品列表子项",
                        options={
                            "parent_resource_id": prefix + "recycler_view",
                            "clickable": True,
                            "pick": "random",
                        },
                    ),
                ),
                follow_target=target("快手关注", id_locator("关注ID", prefix + "follow_button")),
            ),
        ),
        ad_entry=target(
            "快手广告任务入口",
            # “看广告得金币”是任务标题，真机上的可点击按钮是“领福利”。
            text_locator("广告福利按钮文本", "领福利", region=Rect(0.65, 0.20, 1.0, 0.95)),
            text_locator("广告任务文本", "看广告得金币", priority=21),
            ocr_locator(
                "广告福利按钮OCR",
                "领福利",
                mode="exact",
                region=Rect(0.65, 0.20, 1.0, 0.95),
                priority=80,
            ),
            metadata={"ui_tree_source": tree_source},
        ),
        observation_profile=observation_profile,
    )


def create_plugin() -> ComposedAppPlugin:
    """快手插件入口；当前组合标准奖励任务和视频内容任务。"""

    return create_daily_plugin(kuaishou_spec())
