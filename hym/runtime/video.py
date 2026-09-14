from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from hym.apps.specs import VideoContentSpec
from hym.core.models import Observation
from hym.core.targets import ResolveResult, TargetSpec
from hym.runtime.context import AppContext


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
