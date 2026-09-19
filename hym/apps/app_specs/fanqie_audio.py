"""
番茄畅听业务核对说明

每日流程：启动 -> 签到/收听随机先后 -> 按概率看广告 -> 记录余额和提现门槛 -> 停止应用。

任务与限制：
- 主线选择音频收听，低频确认前台状态，不持续解析 UI。
- 签到每天一次；主动领取“首次听书福利/随时领金币”，广告不挤占主要收听时间。
- 流程结束强制停止应用，防止音频继续在后台播放。

页面与状态标记：
- 首页底栏 ID 为 amn，播放条 e_1/e_4，播放卡片按钮 etq。
- 任务入口为 ewi 或“领现金”，任务页包含“时长赚金币/签到/首次听书福利”。
- 新签到路径或播放控件只在本文件追加标记，不修改公共音频任务。
"""

from __future__ import annotations

from dataclasses import dataclass

from hym.apps.app_specs.common import TaskPagePopupNavigator, text_target
from hym.apps.plugin import ComposedAppPlugin, create_daily_plugin
from hym.apps.specs import (
    AdSpec,
    AppSpec,
    AudioContentSpec,
    BalanceAssetSpec,
    BalanceSpec,
    CheckInSpec,
    CheckInStageSpec,
    NavigationSpec,
    PopupDismissSpec,
    WithdrawalSpec,
)
from hym.apps.targets import (
    coordinate_locator,
    desc_locator,
    id_locator,
    ocr_locator,
    query_locator,
    regex_locator,
    target,
    text_locator,
)
from hym.core.control import TaskScope
from hym.core.models import AppIdentity, Point, Rect, SystemKey, UiTreeSource
from hym.core.pages import ObservationProfile, PageSpec
from hym.runtime.audio import AudioContentTask
from hym.runtime.context import AppContext
from hym.runtime.navigation import NavigationController
from hym.runtime.workflow import StepDefinition, StepOutcome


def fanqie_audio_spec() -> AppSpec:
    package_name = "com.xs.fm"
    prefix = f"{package_name}:id/"
    profile = ObservationProfile(UiTreeSource.APPLICATION)

    home_tab = target(
        "番茄畅听首页标签",
        id_locator("首页底栏ID", prefix + "amn"),
        text_locator("首页底栏文本", "首页", region=Rect(0.0, 0.90, 0.25, 1.0)),
        coordinate_locator("首页底栏坐标", Point(0.10, 0.97)),
        required=True,
    )
    home_marker = target(
        "番茄畅听首页内容",
        id_locator("音频播放卡片ID", prefix + "etq"),
        id_locator("底部播放条ID", prefix + "e_1", priority=11),
        required=True,
    )
    task_entry = target(
        "番茄畅听领现金入口",
        id_locator("领现金底栏ID", prefix + "ewi"),
        text_locator("领现金底栏文本", "领现金", region=Rect(0.52, 0.90, 0.82, 1.0)),
        coordinate_locator("领现金底栏坐标", Point(0.70, 0.97)),
        required=True,
    )
    task_marker = target(
        "番茄畅听任务页标记",
        text_locator("时长赚金币文本", "时长赚金币", contains=True),
        text_locator("首次听书福利文本", "首次听书福利", contains=True, priority=21),
        text_locator("连续听书福利文本", "连续听书福利", contains=True, priority=22),
        text_locator("签到文本", "签到", priority=21),
        ocr_locator("时长赚金币OCR", "时长赚金币", confidence=0.45),
        ocr_locator("首次听书福利OCR", "首次听书福利", confidence=0.45, priority=81),
        required=True,
    )
    resume_target = target(
        "番茄畅听恢复播放",
        query_locator(
            "底部播放条可点击ID",
            priority=10,
            options={"resource_id": prefix + "e_1", "clickable": True},
        ),
        query_locator(
            "音频卡片播放按钮",
            priority=11,
            options={"resource_id": prefix + "etq", "clickable": True, "pick": "random"},
        ),
        required=True,
    )
    playing_target = target(
        "番茄畅听正在播放",
        desc_locator("暂停播放描述", "暂停播放"),
        query_locator("暂停状态描述", options={"contains_desc": "暂停"}, priority=21),
    )
    session_marker = target(
        "番茄畅听播放会话",
        id_locator("播放标题ID", prefix + "e_4"),
        id_locator("底部播放条ID", prefix + "e_1", priority=11),
        required=True,
    )
    ad_close = target(
        "番茄畅听广告关闭",
        desc_locator("广告关闭描述", "关闭"),
        coordinate_locator("广告右上角关闭坐标", Point(0.94, 0.06)),
    )
    ad = AdSpec(
        start_markers=(
            text_target("番茄畅听广告倒计时", "秒后可领奖励", contains=True),
            text_target("番茄畅听广告页面", "广告", contains=True),
        ),
        completion_markers=(
            text_target("番茄畅听广告到账", "领取成功", contains=True),
            text_target("番茄畅听广告奖励获得", "已获得", contains=True),
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
        identity=AppIdentity("fanqie_audio", package_name, "番茄畅听", "1.0.0"),
        display_name="番茄畅听",
        navigation=NavigationSpec(
            home_marker=home_marker,
            home_tab=home_tab,
            task_entry=task_entry,
            task_marker=task_marker,
            reselect_home_tab=False,
            home_page=PageSpec(
                "fanqie_audio.home",
                package_name,
                (home_tab, home_marker),
                minimum_markers=2,
                observation_profile=profile,
            ),
            task_page=PageSpec(
                "fanqie_audio.task",
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
                            "番茄畅听签到按钮",
                            text_locator("立即签到文本", "立即签到"),
                            text_locator("签到文本", "签到", priority=21),
                            ocr_locator("立即签到OCR", "立即签到", confidence=0.45),
                        ),
                    ),
                ),
            ),
            success_targets=(
                target(
                    "番茄畅听签到成功",
                    text_locator("已签到文本", "已签到", contains=True),
                    text_locator("明日再来文本", "明日再来", priority=21),
                    regex_locator("连续签到天数", r"已连续签到[1-9]\d*天", priority=22),
                    required=True,
                ),
            ),
            passive_success_targets=(
                target(
                    "番茄畅听今日签到已领取",
                    text_locator("明天领取文本", "明天领取"),
                    ocr_locator("明天领取OCR", "明天领取", confidence=0.45),
                ),
            ),
        ),
        balance=BalanceSpec(
            assets=(
                BalanceAssetSpec(
                    "coin",
                    "金币",
                    target(
                        "番茄畅听金币余额",
                        regex_locator(
                            "金币余额文本",
                            r"^\d+(?:\.\d+)?$",
                            region=Rect(0.03, 0.11, 0.40, 0.21),
                        ),
                        ocr_locator(
                            "金币余额OCR",
                            r"\d+(?:\.\d+)?\s*金币",
                            mode="regex",
                            region=Rect(0.03, 0.11, 0.40, 0.21),
                            confidence=0.25,
                        ),
                    ),
                    unit="金币",
                ),
                BalanceAssetSpec(
                    "cash",
                    "现金",
                    target(
                        "番茄畅听现金余额",
                        regex_locator(
                            "现金余额文本",
                            r"^\d+(?:\.\d+)?$",
                            region=Rect(0.43, 0.11, 0.82, 0.21),
                        ),
                        ocr_locator(
                            "现金余额OCR",
                            r"\d+(?:\.\d+)?\s*元",
                            mode="regex",
                            region=Rect(0.43, 0.11, 0.82, 0.21),
                            confidence=0.25,
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
                    "番茄畅听提现入口",
                    text_locator("现金收益文本", "现金收益", contains=True),
                    coordinate_locator("顶部现金区域坐标", Point(0.62, 0.16)),
                ),
            ),
            dismiss_popups=(
                PopupDismissSpec(
                    marker=text_target("番茄畅听现金奖励弹窗", "开出现金奖励", contains=True),
                    close_target=text_target("番茄畅听现金奖励收下", "开心收下"),
                ),
            ),
            available_region=Rect(0.25, 0.12, 0.72, 0.27),
        ),
        ad=ad,
        ad_entry=target(
            "番茄畅听广告奖励入口",
            text_locator("看视频赚金币文本", "看视频", contains=True),
            ocr_locator("看视频赚金币OCR", "看视频", confidence=0.45),
        ),
        duration_reward=None,
        content=AudioContentSpec(resume_target, playing_target, session_marker),
        observation_profile=profile,
    )


@dataclass(frozen=True, slots=True)
class FanqieAudioPlayback:
    """播放条状态不完整时，允许从当前书籍或播放条恢复一次。"""

    def ensure_playing(self, context: AppContext, spec: AudioContentSpec) -> bool:
        for attempt in range(2):
            observation = context.actions.observe_for(
                (spec.playing_target, spec.resume_target, spec.session_marker),
                include_screenshot=False,
            )
            if observation is not None:
                session = context.actions.resolve_in(spec.session_marker, observation)
                if session.found:
                    if context.actions.resolve_in(spec.playing_target, observation).found:
                        return True
                    # 番茄畅听会自动续播；播放条已出现时不反向点击成暂停。
                    return True
                resume = context.actions.resolve_in(spec.resume_target, observation)
                if resume.found and resume.target is not None:
                    if context.actions.tap_resolved(resume.target):
                        context.timing.operation_delay()
                        return True
            if attempt == 0:
                context.timing.operation_delay()
        return False


@dataclass(frozen=True, slots=True)
class FanqieAudioStopTask:
    app: AppIdentity

    def run(self, context: AppContext) -> StepOutcome:
        result = context.session.stop_app(self.app)
        if not result.succeeded:
            return StepOutcome.failure(f"停止番茄畅听失败: {result.message}")
        return StepOutcome.success("番茄畅听已停止，后台音频已结束")


@dataclass(frozen=True, slots=True)
class FanqieAudioClaimTask:
    """领取已经满足条件的听书金币，不触碰提现和新人现金入口。"""

    task_page: TaskPagePopupNavigator

    def run(self, context: AppContext) -> StepOutcome:
        claim_targets = (
            target(
                "番茄畅听首次听书福利",
                text_locator(
                    "首次听书立即领取文本",
                    "立即领取",
                    region=Rect(0.70, 0.60, 0.98, 0.71),
                ),
                ocr_locator(
                    "首次听书立即领取OCR",
                    "立即领取",
                    region=Rect(0.70, 0.60, 0.98, 0.71),
                    confidence=0.45,
                ),
            ),
            target(
                "番茄畅听随时领金币",
                text_locator(
                    "随时领立即领取文本",
                    "立即领取",
                    region=Rect(0.70, 0.24, 0.98, 0.34),
                ),
                ocr_locator(
                    "随时领立即领取OCR",
                    "立即领取",
                    region=Rect(0.70, 0.24, 0.98, 0.34),
                    confidence=0.45,
                ),
            ),
        )
        claimed: list[str] = []
        for claim_target in claim_targets:
            if not self.task_page(context):
                break
            if context.actions.tap_target(claim_target, timeout=1.5):
                claimed.append(claim_target.target_id)
                context.timing.operation_delay()
                # 领取结果层文案会变化，返回后再由任务页导航恢复。
                context.actions.press(SystemKey.BACK)
                context.timing.operation_delay()
        if not claimed:
            return StepOutcome.skipped("当前没有可领取的听书奖励")
        return StepOutcome.success("听书奖励领取完成", claimed_targets=claimed)


def create_plugin() -> ComposedAppPlugin:
    spec = fanqie_audio_spec()
    navigation = NavigationController(spec)
    audio = spec.audio
    if audio is None:
        raise ValueError("番茄畅听缺少音频规格")
    task_popup = PopupDismissSpec(
        marker=text_target("番茄畅听抽奖弹窗", "天天抽奖赢金币", contains=True),
        close_target=target(
            "番茄畅听抽奖弹窗关闭",
            coordinate_locator("抽奖弹窗底部关闭坐标", Point(0.50, 0.76)),
        ),
    )
    claim_popup = PopupDismissSpec(
        marker=target(
            "番茄畅听领取结果弹窗",
            text_locator("恭喜获得文本", "恭喜获得", contains=True),
            text_locator("领取成功文本", "领取成功", contains=True, priority=21),
            ocr_locator("恭喜获得OCR", "恭喜获得", confidence=0.45),
        ),
        close_target=target(
            "番茄畅听领取结果弹窗关闭",
            text_locator("开心收下文本", "开心收下"),
            text_locator("我知道了文本", "我知道了", priority=21),
            coordinate_locator("领取结果底部关闭坐标", Point(0.50, 0.80)),
        ),
    )
    task_page = TaskPagePopupNavigator(
        navigation,
        (task_popup, claim_popup),
        check_after_entry=True,
    )
    content = AudioContentTask(
        spec.identity,
        audio,
        navigation,
        FanqieAudioPlayback(),
    )
    stop = FanqieAudioStopTask(spec.identity)
    return create_daily_plugin(
        spec,
        navigation=navigation,
        task_page_navigator=task_page,
        content_handler=content.run,
        extra_steps=lambda _: (
            StepDefinition(
                "领取听书奖励",
                "领取已赚听书奖励",
                FanqieAudioClaimTask(task_page).run,
                recovery=navigation.recover_home,
                task_scope=TaskScope.FULL_ONLY,
            ),
        ),
        cleanup_steps=lambda _: (
            StepDefinition(
                "停止应用",
                "停止番茄畅听",
                stop.run,
                max_attempts=2,
                capture_on_failure=False,
                allow_interruption_after=False,
                task_scope=TaskScope.CLEANUP,
            ),
        ),
    )
