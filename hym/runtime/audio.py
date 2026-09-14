from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from hym.apps.specs import AudioContentSpec
from hym.core.events import EventLevel
from hym.core.models import AppIdentity
from hym.runtime.context import AppContext
from hym.runtime.navigation import NavigationController
from hym.runtime.workflow import StepOutcome


class AudioPlayback(Protocol):
    """音频播放入口策略，App 可以注入自己的加载与恢复规则。"""

    def ensure_playing(self, context: AppContext, spec: AudioContentSpec) -> bool: ...


@dataclass(frozen=True, slots=True)
class DefaultAudioPlayback:
    """接受正在播放状态，否则点击一次恢复播放。"""

    def ensure_playing(self, context: AppContext, spec: AudioContentSpec) -> bool:
        observation = context.actions.observe_for(
            (spec.resume_target, spec.playing_target, spec.session_marker),
            include_screenshot=False,
        )
        if observation is None or not context.actions.resolve_in(
            spec.session_marker,
            observation,
        ).found:
            return False
        if context.actions.resolve_in(spec.playing_target, observation).found:
            return True
        resume = context.actions.resolve_in(spec.resume_target, observation)
        if not resume.found or resume.target is None:
            return False
        if not context.actions.tap_resolved(resume.target):
            return False
        context.timing.operation_delay()
        return True


@dataclass(frozen=True, slots=True)
class AudioContentTask:
    """运行长时音频会话，并按低频检查点恢复播放。"""

    app: AppIdentity
    spec: AudioContentSpec
    navigation: NavigationController
    playback: AudioPlayback

    def run(self, context: AppContext) -> StepOutcome:
        if not self.navigation.go_home(context, select_tab=True):
            return StepOutcome.failure("音频播放前无法进入首页")
        if not self.playback.ensure_playing(context, self.spec):
            return StepOutcome.failure("没有识别到可播放的音频会话")

        progress = context.step_progress("浏览内容")
        if "target_seconds" not in progress:
            progress.update(
                {
                    "content_kind": "audio",
                    "target_seconds": context.sample_seconds(
                        "audio_session_seconds",
                        600.0,
                        1800.0,
                    ),
                    "elapsed_seconds": 0.0,
                    "recovery_count": 0,
                }
            )
        duration = float(progress["target_seconds"])
        check_interval = max(
            15.0,
            float(context.option("audio_check_interval_seconds", 60.0)),
        )
        context.emit(
            "content.audio.session.started",
            "音频会话开始",
            "音频已开始播放，进入低频状态确认",
            workflow_id="daily",
            step_id="浏览内容",
            status="running",
            data={
                "planned_seconds": round(duration, 2),
                "check_interval_seconds": check_interval,
            },
        )
        elapsed = float(progress.get("elapsed_seconds", 0.0))
        recoveries = int(progress.get("recovery_count", 0))
        while elapsed < duration:
            wait_seconds = min(check_interval, duration - elapsed)
            context.timing.clock.sleep(wait_seconds)
            elapsed += wait_seconds
            # 长时任务只检查前台包名，不在正常路径持续解析 UI。
            current = context.actions.observe(include_ui_tree=False, include_screenshot=False)
            if current is not None and current.activity.package_name == self.app.package_name:
                progress["elapsed_seconds"] = elapsed
                context.reach_safe_point(
                    "content.audio.checkpoint",
                    elapsed_seconds=round(elapsed, 2),
                    target_seconds=round(duration, 2),
                )
                continue
            recoveries += 1
            context.emit(
                "content.audio.session.recovering",
                "音频会话恢复",
                "音频会话离开目标应用，尝试恢复播放",
                level=EventLevel.WARNING,
                workflow_id="daily",
                step_id="浏览内容",
                status="recovering",
                data={
                    "recovery_count": recoveries,
                    "foreground_package": current.activity.package_name if current else "",
                    "foreground_activity": current.activity.activity_name if current else "",
                },
            )
            if not self.navigation.go_home(context, select_tab=True):
                return StepOutcome.failure("音频会话离开应用且恢复失败")
            if not self.playback.ensure_playing(context, self.spec):
                return StepOutcome.failure("音频会话恢复后无法继续播放")
            progress["elapsed_seconds"] = elapsed
            progress["recovery_count"] = recoveries
            context.reach_safe_point(
                "content.audio.checkpoint",
                elapsed_seconds=round(elapsed, 2),
                target_seconds=round(duration, 2),
            )

        context.clear_step_progress("浏览内容")
        return StepOutcome.success(
            "音频浏览会话完成",
            listened_seconds=round(duration, 2),
            recovery_count=recoveries,
        )
