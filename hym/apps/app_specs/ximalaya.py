"""
喜马拉雅极速版业务核对说明

维护约定：
- 同一个 target(...) 内的 ID、描述和查询条件是“任选一个命中”。
- 同一播放状态出现新 ID/描述时，在原 target 内追加 locator；出现新的播放页面或奖励流程时，
  才新增 target 或专用步骤。保留旧标记，target_id 和策略名称不要随意改名，便于查日志。

阅读与调参：
- 本文件从上到下依次声明首页、播放状态、音频会话和喜马拉雅独有的冷启动恢复；
  target 和 locator 的中文名称会原样进入日志，可直接对应真机命中过程。
- 会话参数在 config/automation.json 的 ximalaya.options 调整：audio_session_seconds_* 控制收听时长，
  audio_check_interval_seconds 控制低频检查间隔，skip_content 可临时跳过音频任务。

每日流程：启动应用 -> 回到首页 -> 恢复或确认播放 -> 保持一段音频会话 -> 停止应用。

任务与限制：
- 当前只听书，不执行签到、余额、时段奖励和广告任务。
- 音频会话时长和检查间隔由配置控制，不做高频 UI 解析。
- 低频发现应用离开前台后才回首页；App 已自动续播时直接继续，否则点击恢复播放。
- 冷启动后播放条可能晚于首页出现，仅在首次缺失时由本 App 播放策略短暂重试一次。
- 音频任务结束后强制停止喜马拉雅，避免流程完成后继续在后台播放。
- WelComeActivity 是已知过渡页，允许有限等待；恢复失败会记录当时前台包名和 Activity。

页面与状态标记：
- 主界面：host_main_activity_root_view。
- 首页：main_home_page_root_view；首页标签：tab_home。
- 可恢复播放：main_sound_cover_img 的描述包含“开始播放”。
- 已在播放：同一节点的描述包含“暂停播放”。
- 播放会话：host_round_progressbar_play_progress。
- 正常首页 Activity 为 MainActivity；WelComeActivity 只视为启动过渡页。

待持续校准：后续增加签到或领取奖励时，在本文件补业务分支和标记，不改音频公共执行器。
"""

from __future__ import annotations

from dataclasses import dataclass

from hym.apps.specs import AppSpec, AudioContentSpec, NavigationSpec
from hym.apps.plugin import ComposedAppPlugin, create_daily_plugin
from hym.apps.targets import id_locator, query_locator, target
from hym.core.models import AppIdentity, UiTreeSource
from hym.core.pages import ObservationProfile, PageSpec
from hym.runtime.audio import AudioContentTask, AudioPlayback, DefaultAudioPlayback
from hym.runtime.context import AppContext
from hym.runtime.navigation import NavigationController
from hym.runtime.workflow import StepDefinition, StepOutcome


def ximalaya_spec() -> AppSpec:
    package_name = "com.ximalaya.ting.lite"
    prefix = f"{package_name}:id/"
    observation_profile = ObservationProfile(UiTreeSource.INSTRUMENTATION)

    # 页面与导航标记；同一 target 内可继续追加新版 ID 或描述作为备选
    app_root = target(
        "喜马拉雅主界面",
        id_locator("主界面ID", prefix + "host_main_activity_root_view"),
    )
    home_marker = target(
        "喜马拉雅首页标记",
        id_locator("首页根节点ID", prefix + "main_home_page_root_view"),
        required=True,
    )
    home_tab = target(
        "喜马拉雅首页标签",
        id_locator("首页标签ID", prefix + "tab_home"),
        required=True,
    )

    # 播放按钮用无障碍描述区分“需要恢复”和“正在播放”两种状态
    play_button_id = prefix + "main_sound_cover_img"
    resume_target = target(
        "喜马拉雅开始播放",
        query_locator(
            "播放按钮状态",
            options={
                "resource_id": play_button_id,
                "contains_desc": "开始播放",
                "clickable": True,
            },
        ),
    )
    playing_target = target(
        "喜马拉雅正在播放",
        query_locator(
            "暂停按钮状态",
            options={
                "resource_id": play_button_id,
                "contains_desc": "暂停播放",
            },
        ),
        required=True,
    )
    session_marker = target(
        "喜马拉雅播放会话",
        id_locator("播放进度ID", prefix + "host_round_progressbar_play_progress"),
        required=True,
    )

    return AppSpec(
        identity=AppIdentity("ximalaya", package_name, "喜马拉雅极速版", "1.0.0"),
        display_name="喜马拉雅极速版",
        navigation=NavigationSpec(
            home_marker=home_marker,
            home_tab=home_tab,
            home_attempts=8,
            transient_activity_patterns=(r"WelComeActivity$",),
            home_page=PageSpec(
                "ximalaya.home",
                package_name,
                (app_root, home_marker),
                activity_patterns=(r"MainActivity$",),
                minimum_markers=2,
                observation_profile=observation_profile,
            ),
        ),
        check_in=None,
        balance=None,
        ad=None,
        duration_reward=None,
        content=AudioContentSpec(
            resume_target=resume_target,
            playing_target=playing_target,
            session_marker=session_marker,
        ),
        observation_profile=observation_profile,
        metadata={"validated_activity": "com.ximalaya.ting.android.host.activity.MainActivity"},
    )


@dataclass(frozen=True, slots=True)
class XimalayaPlayback:
    """喜马拉雅冷启动后允许播放控件短暂延迟。"""

    fallback: AudioPlayback

    def ensure_playing(self, context: AppContext, spec: AudioContentSpec) -> bool:
        if self.fallback.ensure_playing(context, spec):
            return True
        context.emit(
            "content.audio.controls.waiting",
            "等待播放控件",
            "首页已进入，等待播放控件完成加载",
            workflow_id="daily",
            step_id="浏览内容",
            status="waiting",
        )
        context.timing.operation_delay()
        return self.fallback.ensure_playing(context, spec)


@dataclass(frozen=True, slots=True)
class XimalayaStopTask:
    """结束本轮任务后停止应用，确保后台音频同步结束。"""

    app: AppIdentity

    def run(self, context: AppContext) -> StepOutcome:
        result = context.session.stop_app(self.app)
        if not result.succeeded:
            return StepOutcome.failure(f"停止喜马拉雅失败: {result.message}")
        return StepOutcome.success("喜马拉雅已停止，后台音频已结束")


def create_plugin() -> ComposedAppPlugin:
    """组合音频会话、专用播放入口和 App 级停止步骤。"""

    spec = ximalaya_spec()
    navigation = NavigationController(spec)
    audio = spec.audio
    if audio is None:
        raise ValueError("喜马拉雅缺少音频内容规格")
    content = AudioContentTask(
        spec.identity,
        audio,
        navigation,
        XimalayaPlayback(DefaultAudioPlayback()),
    )
    stop_task = XimalayaStopTask(spec.identity)
    return create_daily_plugin(
        spec,
        navigation=navigation,
        content_handler=content.run,
        extra_steps=lambda _: (
            StepDefinition(
                "停止应用",
                "停止喜马拉雅",
                stop_task.run,
                max_attempts=2,
                capture_on_failure=False,
                allow_interruption_after=False,
            ),
        ),
    )
