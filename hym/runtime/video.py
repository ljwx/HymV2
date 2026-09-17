from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum

from hym.apps.specs import VideoContentSpec
from hym.core.events import EventLevel
from hym.core.models import AppIdentity, Observation, SystemKey, WorkflowStatus
from hym.core.targets import ResolveResult, TargetSpec
from hym.runtime.context import AppContext
from hym.runtime.navigation import NavigationController
from hym.runtime.workflow import StepOutcome


class VideoContentKind(str, Enum):
    """视频内容的稳定内部类型，中文名称只用于展示。"""

    AD = "ad"
    SUSPECTED_AD = "suspected_ad"
    LONG = "long"
    NORMAL = "normal"
    UNCLASSIFIED = "unclassified"

    @property
    def label(self) -> str:
        return {
            self.AD: "广告内容",
            self.SUSPECTED_AD: "疑似广告",
            self.LONG: "长视频",
            self.NORMAL: "普通视频",
            self.UNCLASSIFIED: "未分类视频",
        }[self]


@dataclass(frozen=True, slots=True)
class VideoClassification:
    kind: VideoContentKind
    reason: str
    matched_target_id: str | None = None
    allow_interactions: bool = False


@dataclass(frozen=True, slots=True)
class VideoWatchPlan:
    mode: str
    duration_prefix: str
    duration_range: tuple[float, float]
    post_classification_minimum: float = 0.0
    allow_interactions: bool = False


class VideoContentClassifier:
    """组合结构和视觉标记完成分类，不决定观看时间。"""

    def classify(
        self,
        context: AppContext,
        spec: VideoContentSpec,
        observation: Observation,
    ) -> VideoClassification:
        classified = self._resolve_first_in(
            context,
            (*spec.ad_markers, *spec.long_markers, *spec.normal_markers),
            observation,
        )
        matched_id = classified[0].target_id if classified is not None else None
        known_ad = self._contains_target(spec.ad_markers, matched_id)

        # 结构标记未确认广告时才补一次视觉检查，视觉广告可以覆盖普通内容标记。
        if not known_ad:
            visual_ad_targets = tuple(
                target
                for target in spec.ad_markers
                if context.actions.needs_screenshot((target,))
            )
            if visual_ad_targets:
                visual_ad = context.actions.resolve_many(
                    visual_ad_targets,
                    include_screenshot=True,
                    # 结构定位已使用上一份观察完成，这里只补视觉证据。
                    include_ui_tree=False,
                    screenshot_max_size=int(context.option("video_ocr_max_size", 960)),
                )
                if visual_ad is not None:
                    classified = visual_ad

        if classified is None:
            if bool(context.option("treat_unclassified_as_suspected_ad", False)):
                return VideoClassification(
                    VideoContentKind.SUSPECTED_AD,
                    "关键分类标记未命中",
                )
            return VideoClassification(
                VideoContentKind.UNCLASSIFIED,
                "关键分类标记未命中",
                allow_interactions=bool(
                    context.option("interact_unclassified_video", False)
                ),
            )

        matched_id = classified[0].target_id
        if self._contains_target(spec.ad_markers, matched_id):
            return VideoClassification(
                VideoContentKind.AD,
                "广告标记命中",
                matched_id,
            )
        if self._contains_target(spec.long_markers, matched_id):
            return VideoClassification(
                VideoContentKind.LONG,
                "长视频标记命中",
                matched_id,
                True,
            )
        return VideoClassification(
            VideoContentKind.NORMAL,
            "普通视频标记命中",
            matched_id,
            True,
        )

    @staticmethod
    def _resolve_first_in(
        context: AppContext,
        targets: Sequence[TargetSpec],
        observation: Observation,
    ) -> tuple[TargetSpec, ResolveResult] | None:
        for target in targets:
            result = context.actions.resolve_in(target, observation)
            if result.found:
                return target, result
        return None

    @staticmethod
    def _contains_target(
        targets: Sequence[TargetSpec],
        target_id: str | None,
    ) -> bool:
        return any(target.target_id == target_id for target in targets)


class VideoWatchPlanner:
    """按内容类型选择观看节奏，不负责页面识别和滑动。"""

    def plan(
        self,
        context: AppContext,
        *,
        classification: VideoClassification,
    ) -> VideoWatchPlan:
        kind = classification.kind
        if kind is VideoContentKind.AD:
            return VideoWatchPlan("广告短暂停留", "inline_ad_duration", (0.5, 2.5))
        if kind is VideoContentKind.SUSPECTED_AD:
            return VideoWatchPlan(
                "疑似广告快速划过",
                "suspected_ad_duration",
                (1.0, 4.0),
            )
        if kind is VideoContentKind.LONG:
            return VideoWatchPlan(
                "长内容观看",
                "long_duration",
                (15.0, 75.0),
                float(context.option("long_post_classification_min_seconds", 8.0)),
                classification.allow_interactions,
            )
        if kind is VideoContentKind.UNCLASSIFIED:
            return VideoWatchPlan(
                "未分类保守观看",
                "unclassified_duration",
                (6.0, 14.0),
                float(context.option("unclassified_post_classification_min_seconds", 4.0)),
                classification.allow_interactions,
            )

        uninterested_probability = float(
            context.option("uninterested_video_probability", 0.08)
        )
        full_watch_probability = float(
            context.option("full_watch_attempt_probability", 0.25)
        )
        decision = context.random.random()
        if decision < uninterested_probability:
            return VideoWatchPlan(
                "低概率快速划过",
                "uninterested_duration",
                (3.0, 7.0),
            )
        if decision < uninterested_probability + full_watch_probability:
            # 没有可靠结束信号时，用较长停留覆盖多数短视频，但不宣称已确认看完。
            return VideoWatchPlan(
                "完整观看尝试",
                "full_watch_fallback_duration",
                (25.0, 65.0),
                float(context.option("full_watch_post_classification_min_seconds", 10.0)),
                classification.allow_interactions,
            )
        return VideoWatchPlan(
            "常规观看",
            "normal_duration",
            (10.0, 30.0),
            float(context.option("normal_post_classification_min_seconds", 5.0)),
            classification.allow_interactions,
        )


@dataclass(slots=True)
class VideoContentTask:
    """执行视频流浏览；App 只提供分类标记和交互目标。"""

    app: AppIdentity
    spec: VideoContentSpec
    navigation: NavigationController
    classifier: VideoContentClassifier = field(default_factory=VideoContentClassifier)
    watch_planner: VideoWatchPlanner = field(default_factory=VideoWatchPlanner)

    def run(self, context: AppContext) -> StepOutcome:
        if not self.navigation.go_home(context, select_tab=True):
            return StepOutcome.failure("无法进入视频首页")
        progress = context.step_progress("浏览内容")
        if "target_count" not in progress:
            progress.update(
                {
                    "content_kind": "video",
                    "target_count": context.sample_count("content_count", 5, 26),
                    "next_index": 1,
                    "viewed": 0,
                    "normal": 0,
                    "unrecognized_streak": 0,
                }
            )
        count = int(progress["target_count"])
        viewed = int(progress.get("viewed", 0))
        normal_count = int(progress.get("normal", 0))
        unrecognized_streak = int(progress.get("unrecognized_streak", 0))
        recover_after = int(context.option("recover_after_unrecognized_items", 2))
        for index in range(int(progress.get("next_index", 1)), count + 1):
            item_started = context.timing.clock.now()
            context.actions.swipe_up()
            context.timing.clock.sleep(
                context.sample_seconds("content_classify_delay", 0.25, 0.6)
            )
            observation = context.actions.observe_for(
                (
                    self.spec.feed_marker,
                    *self.spec.ad_markers,
                    *self.spec.long_markers,
                    *self.spec.normal_markers,
                ),
                include_screenshot=False,
            )
            if (
                observation is not None
                and observation.activity.package_name
                and observation.activity.package_name != self.app.package_name
            ):
                context.emit(
                    "content.foreground.left",
                    "内容页离开应用",
                    f"第 {index} 个内容跳到其他应用，开始恢复首页",
                    level=EventLevel.WARNING,
                    workflow_id="daily",
                    step_id="浏览内容",
                    status="recovering",
                    data={
                        "index": index,
                        "foreground_package": observation.activity.package_name,
                    },
                )
                self.navigation.recover_home(context)
                continue
            if observation is None or not context.actions.resolve_in(
                self.spec.feed_marker,
                observation,
            ).found:
                if observation is not None:
                    target_id = self.navigation.dismiss_popup_in(
                        context,
                        self.navigation.spec.navigation.home_intercepts,
                        observation,
                    )
                    if target_id is not None:
                        self.navigation.emit_popup_dismissed(context, target_id)
                        context.timing.operation_delay()
                        unrecognized_streak = 0
                        continue
                unrecognized_streak += 1
                context.emit(
                    "content.item.skipped",
                    "内容跳过",
                    f"第 {index} 个内容不是可识别的视频项",
                    level=EventLevel.WARNING,
                    workflow_id="daily",
                    step_id="浏览内容",
                    status="skipped",
                    data={"index": index},
                )
                if unrecognized_streak >= recover_after:
                    self.navigation.recover_home(context)
                    unrecognized_streak = 0
                continue

            unrecognized_streak = 0
            classification = self.classifier.classify(context, self.spec, observation)
            watch_plan = self.watch_planner.plan(context, classification=classification)
            target_duration = context.sample_seconds(
                watch_plan.duration_prefix,
                *watch_plan.duration_range,
            )
            classification_seconds = max(
                0.0,
                (context.timing.clock.now() - item_started).total_seconds(),
            )
            if classification.kind in {VideoContentKind.AD, VideoContentKind.SUSPECTED_AD}:
                self._emit_ad_classification(
                    context,
                    index,
                    classification,
                    classification_seconds,
                )
            minimum_after_classification = (
                context.timing.baseline_seconds(watch_plan.post_classification_minimum)
                if watch_plan.post_classification_minimum > 0
                else 0.0
            )
            remaining = max(
                0.0,
                target_duration - classification_seconds,
                minimum_after_classification,
            )
            if remaining > 0:
                context.timing.clock.sleep(remaining)
            duration = max(
                0.0,
                (context.timing.clock.now() - item_started).total_seconds(),
            )
            viewed += 1
            if classification.kind in {VideoContentKind.NORMAL, VideoContentKind.LONG}:
                normal_count += 1
            if watch_plan.allow_interactions:
                self._run_interactions(context)
            self._emit_item_finished(
                context,
                index,
                classification,
                watch_plan,
                target_duration,
                duration,
                classification_seconds,
                remaining,
            )
            progress.update(
                {
                    "next_index": index + 1,
                    "viewed": viewed,
                    "normal": normal_count,
                    "unrecognized_streak": unrecognized_streak,
                }
            )
            context.reach_safe_point(
                "content.item.finished",
                index=index,
                requested=count,
                viewed=viewed,
            )

        if viewed == 0:
            context.clear_step_progress("浏览内容")
            return StepOutcome(
                WorkflowStatus.NO_PROGRESS,
                "本轮没有完成任何视频浏览",
                {"requested": count},
            )
        context.clear_step_progress("浏览内容")
        return StepOutcome.success(
            "视频浏览完成",
            requested=count,
            viewed=viewed,
            normal=normal_count,
        )

    @staticmethod
    def _emit_ad_classification(
        context: AppContext,
        index: int,
        classification: VideoClassification,
        classification_seconds: float,
    ) -> None:
        suspected = classification.kind is VideoContentKind.SUSPECTED_AD
        context.emit(
            "content.ad.suspected" if suspected else "content.ad.detected",
            "疑似视频广告" if suspected else "视频广告识别",
            (
                f"第 {index} 个内容缺少明确分类标记，按疑似广告快速跳过"
                if suspected
                else f"第 {index} 个内容识别为广告，禁止互动"
            ),
            workflow_id="daily",
            step_id="浏览内容",
            status="success",
            data={
                "index": index,
                "classification_seconds": round(classification_seconds, 2),
                "classification_kind": classification.kind.value,
                "classification_reason": classification.reason,
                "matched_target_id": classification.matched_target_id,
            },
        )

    @staticmethod
    def _emit_item_finished(
        context: AppContext,
        index: int,
        classification: VideoClassification,
        watch_plan: VideoWatchPlan,
        target_duration: float,
        duration: float,
        classification_seconds: float,
        remaining: float,
    ) -> None:
        context.emit(
            "content.item.finished",
            "内容浏览完成",
            f"第 {index} 个内容浏览完成，类型: {classification.kind.label}",
            workflow_id="daily",
            step_id="浏览内容",
            status="success",
            data={
                "index": index,
                "content_type": classification.kind.label,
                "classification_kind": classification.kind.value,
                "classification_reason": classification.reason,
                "watch_mode": watch_plan.mode,
                "planned_duration_seconds": round(target_duration, 2),
                "duration_seconds": round(duration, 2),
                "classification_seconds": round(classification_seconds, 2),
                "post_classification_wait_seconds": round(remaining, 2),
                "video_length_detected": False,
                "matched_target_id": classification.matched_target_id,
            },
        )

    def _run_interactions(self, context: AppContext) -> None:
        interaction = self.spec.interaction
        if interaction.follow_target is not None and context.random.random() < float(
            context.option("follow_probability", 0.002)
        ):
            context.actions.tap_target(interaction.follow_target, timeout=0.8)
        if interaction.like_target is not None and context.random.random() < float(
            context.option("like_probability", 0.17)
        ):
            context.actions.tap_target(interaction.like_target, timeout=1.0)
            context.timing.operation_delay()
        if interaction.comment_target is not None and context.random.random() < float(
            context.option("comment_probability", 0.05)
        ):
            if context.actions.tap_target(interaction.comment_target, timeout=1.0):
                context.timing.operation_delay(2)
                context.actions.press(SystemKey.BACK)
                context.timing.operation_delay()
        if interaction.profile_target is not None and context.random.random() < float(
            context.option("works_probability", 0.12)
        ):
            self._browse_author_works(context)

    def _browse_author_works(self, context: AppContext) -> None:
        interaction = self.spec.interaction
        if interaction.profile_target is None or not context.actions.tap_target(
            interaction.profile_target,
            timeout=1.0,
        ):
            return
        context.timing.operation_delay()
        if interaction.profile_marker is not None and not context.actions.exists(
            interaction.profile_marker,
            timeout=2.0,
        ):
            context.actions.press(SystemKey.BACK)
            return
        count = context.sample_count("works_count", 1, 5)
        for _ in range(count):
            if interaction.work_item_target is None or not context.actions.tap_target(
                interaction.work_item_target,
                timeout=1.5,
            ):
                context.actions.swipe_up()
                continue
            context.timing.clock.sleep(
                context.sample_seconds("normal_duration", 10.0, 30.0)
            )
            context.actions.press(SystemKey.BACK)
            context.timing.operation_delay()
            context.actions.swipe_up()
        context.actions.press(SystemKey.BACK)
