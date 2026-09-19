from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, Mapping, TypeAlias

from hym.core.models import AppIdentity, Rect
from hym.core.pages import ObservationProfile, PageSpec
from hym.core.targets import TargetSpec


@dataclass(frozen=True, slots=True)
class PopupDismissSpec:
    """弹窗标记可选；有标记时先确认弹窗，再点击关闭目标。"""

    close_target: TargetSpec
    marker: TargetSpec | None = None


@dataclass(frozen=True, slots=True)
class NavigationSpec:
    home_marker: TargetSpec
    home_tab: TargetSpec
    task_entry: TargetSpec | None = None
    task_marker: TargetSpec | None = None
    launch_dismiss: tuple[TargetSpec, ...] = ()
    launch_intercepts: tuple[PopupDismissSpec, ...] = ()
    home_intercepts: tuple[PopupDismissSpec, ...] = ()
    task_dismiss: tuple[TargetSpec, ...] = ()
    page_wait_seconds: float = 4.0
    home_attempts: int = 5
    reselect_home_tab: bool = True
    select_home_tab_before_task: bool = True
    transient_activity_patterns: tuple[str, ...] = ()
    home_page: PageSpec | None = None
    task_page: PageSpec | None = None

    def __post_init__(self) -> None:
        if (self.task_entry is None) != (self.task_marker is None):
            raise ValueError("任务入口和任务页标记必须同时配置")


@dataclass(frozen=True, slots=True)
class CheckInStageSpec:
    """签到的一种可选状态；多个动作目标是备选关系，页面命中哪个就执行哪个。"""

    stage_id: str
    action_targets: tuple[TargetSpec, ...]
    state_markers: tuple[TargetSpec, ...] = ()
    commit_action: bool = True
    wait_seconds: float | None = None

    def __post_init__(self) -> None:
        if not self.stage_id:
            raise ValueError("签到阶段 ID 不能为空")
        if not self.action_targets:
            raise ValueError(f"签到阶段 {self.stage_id} 至少需要一个动作目标")
        if self.wait_seconds is not None and self.wait_seconds < 0:
            raise ValueError(f"签到阶段 {self.stage_id} 等待时间不能小于零")


@dataclass(frozen=True, slots=True)
class CheckInSpec:
    """按当前页面动态推进签到阶段，不假设每次路径相同。"""

    stages: tuple[CheckInStageSpec, ...]
    success_targets: tuple[TargetSpec, ...]
    # 页面不展示明确完成文案时，仅在没有可执行动作后使用这些证据。
    passive_success_targets: tuple[TargetSpec, ...] = ()
    post_ad_target: TargetSpec | None = None
    close_target: TargetSpec | None = None
    close_with_back: bool = False
    pre_ad_attempts: int = 0
    max_transitions: int = 4

    def __post_init__(self) -> None:
        if not self.stages:
            raise ValueError("签到流程至少需要一个可执行阶段")
        if not self.success_targets:
            raise ValueError("签到流程至少需要一个成功信号")
        if self.max_transitions < 1:
            raise ValueError("签到最大状态转换次数必须大于零")


@dataclass(frozen=True, slots=True)
class BalanceAssetSpec:
    """声明一个可独立展示和比较的余额字段。"""

    asset_key: str
    asset_label: str
    target: TargetSpec
    scale: int = 0
    unit: str = ""

    def __post_init__(self) -> None:
        if not self.asset_key or not self.asset_label:
            raise ValueError("余额字段标识和名称不能为空")
        if not 0 <= self.scale <= 6:
            raise ValueError("余额小数位必须位于 0 到 6 之间")


@dataclass(frozen=True, slots=True)
class BalanceSpec:
    balance_target: TargetSpec | None = None
    assets: tuple[BalanceAssetSpec, ...] = ()
    enter_target: TargetSpec | None = None
    page_marker: TargetSpec | None = None
    screenshot_only: bool = False
    close_with_back: bool = False
    region: Rect | None = None
    enter_wait_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.balance_target is None and not self.assets:
            raise ValueError("余额流程至少需要一个定位目标")
        keys = [asset.asset_key for asset in self.assets]
        if len(keys) != len(set(keys)):
            raise ValueError("余额字段标识不能重复")
        if self.enter_wait_seconds is not None and self.enter_wait_seconds < 0:
            raise ValueError("余额页面等待时间不能小于零")


@dataclass(frozen=True, slots=True)
class WithdrawalSpec:
    """声明提现页入口和金额区域；采集端只上报结构化金额。"""

    entry_sequence: tuple[TargetSpec, ...]
    available_region: Rect
    minimum_region: Rect | None = None
    minimum_amount_minor: int | None = None
    dismiss_popups: tuple[PopupDismissSpec, ...] = ()
    scale: int = 2
    unit: str = "元"
    refresh_days: int = 1
    page_wait_seconds: float = 4.0
    close_back_count: int = 1

    def __post_init__(self) -> None:
        if not self.entry_sequence:
            raise ValueError("提现流程至少需要一个入口")
        if not 0 <= self.scale <= 6:
            raise ValueError("提现金额小数位必须位于 0 到 6 之间")
        if self.minimum_amount_minor is not None and self.minimum_amount_minor < 0:
            raise ValueError("最低提现金额不能小于零")
        if self.refresh_days < 1:
            raise ValueError("提现信息刷新间隔必须大于零")
        if self.page_wait_seconds < 0:
            raise ValueError("提现页面等待时间不能小于零")
        if self.close_back_count < 0:
            raise ValueError("提现页面返回次数不能小于零")


@dataclass(frozen=True, slots=True)
class AdSpec:
    start_markers: tuple[TargetSpec, ...]
    continue_targets: tuple[TargetSpec, ...]
    next_sequences: tuple[tuple[TargetSpec, ...], ...]
    close_targets: tuple[TargetSpec, ...]
    final_close_targets: tuple[TargetSpec, ...]
    exit_targets: tuple[TargetSpec, ...]
    completion_markers: tuple[TargetSpec, ...] = ()
    # 某些 App 只有在广告播放完成后按返回键，才会显示退出确认弹窗。
    exit_after_wait_with_back: bool = False
    exit_prompt_markers: tuple[TargetSpec, ...] = ()
    exit_prompt_continue_targets: tuple[TargetSpec, ...] = ()
    exit_prompt_close_targets: tuple[TargetSpec, ...] = ()
    extra_rounds_min: int = 0
    extra_rounds_max: int = 0
    completion_wait_seconds: float = 35.0
    completion_check_interval_seconds_min: float = 4.0
    completion_check_interval_seconds_center: float = 5.0
    completion_check_interval_seconds_max: float = 6.0
    completion_check_interval_seconds_stddev: float = 0.5
    completion_settle_seconds_min: float = 1.0
    completion_settle_seconds_center: float = 5.0
    completion_settle_seconds_max: float = 10.0
    completion_settle_seconds_stddev: float = 1.5
    entry_attempts: int = 4
    max_cycles: int = 10
    max_back_attempts: int = 3

    def __post_init__(self) -> None:
        if bool(self.exit_prompt_markers) != bool(self.exit_prompt_close_targets):
            raise ValueError("广告退出弹窗标记和关闭目标必须同时配置")
        if self.exit_prompt_continue_targets and not self.exit_prompt_markers:
            raise ValueError("广告续看目标必须配置对应的退出弹窗标记")
        if self.extra_rounds_min < 0 or self.extra_rounds_min > self.extra_rounds_max:
            raise ValueError("广告追加轮数范围无效")
        if self.extra_rounds_max > 0 and not self.exit_prompt_continue_targets:
            raise ValueError("广告追加轮数大于零时必须配置续看目标")
        if self.completion_wait_seconds <= 0:
            raise ValueError("广告等待时间必须大于零")
        if self.completion_check_interval_seconds_min <= 0:
            raise ValueError("广告完成检查间隔必须大于零")
        if (
            self.completion_check_interval_seconds_min
            > self.completion_check_interval_seconds_max
        ):
            raise ValueError("广告完成检查间隔范围无效")
        if not (
            self.completion_check_interval_seconds_min
            <= self.completion_check_interval_seconds_center
            <= self.completion_check_interval_seconds_max
        ):
            raise ValueError("广告完成检查中心值必须位于配置范围内")
        if self.completion_check_interval_seconds_stddev <= 0:
            raise ValueError("广告完成检查标准差必须大于零")
        if self.completion_settle_seconds_min < 0 or (
            self.completion_settle_seconds_min
            > self.completion_settle_seconds_max
        ):
            raise ValueError("广告完成后停留范围无效")
        if not (
            self.completion_settle_seconds_min
            <= self.completion_settle_seconds_center
            <= self.completion_settle_seconds_max
        ):
            raise ValueError("广告完成后停留中心值必须位于配置范围内")
        if self.completion_settle_seconds_stddev <= 0:
            raise ValueError("广告完成后停留标准差必须大于零")


@dataclass(frozen=True, slots=True)
class DurationRewardSpec:
    reward_target: TargetSpec
    success_target: TargetSpec | None = None
    ad_target: TargetSpec | None = None
    close_target: TargetSpec | None = None
    result_wait_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.result_wait_seconds is not None and self.result_wait_seconds < 0:
            raise ValueError("时段奖励结果等待时间不能小于零")


@dataclass(frozen=True, slots=True)
class InteractionSpec:
    like_target: TargetSpec | None = None
    comment_target: TargetSpec | None = None
    profile_target: TargetSpec | None = None
    profile_marker: TargetSpec | None = None
    work_item_target: TargetSpec | None = None
    follow_target: TargetSpec | None = None


@dataclass(frozen=True, slots=True)
class VideoContentSpec:
    kind: str = field(init=False, default="video")
    feed_marker: TargetSpec
    ad_markers: tuple[TargetSpec, ...]
    normal_markers: tuple[TargetSpec, ...]
    long_markers: tuple[TargetSpec, ...]
    interaction: InteractionSpec


@dataclass(frozen=True, slots=True)
class NewsContentSpec:
    kind: str = field(init=False, default="news")
    feed_item: TargetSpec
    detail_marker: TargetSpec
    like_target: TargetSpec | None = None
    comment_target: TargetSpec | None = None
    bottom_marker: TargetSpec | None = None


@dataclass(frozen=True, slots=True)
class AudioContentSpec:
    """长时音频采用会话模型，不按短内容逐条滑动。"""

    kind: str = field(init=False, default="audio")
    resume_target: TargetSpec
    playing_target: TargetSpec
    session_marker: TargetSpec


ContentSpec: TypeAlias = VideoContentSpec | NewsContentSpec | AudioContentSpec


@dataclass(frozen=True, slots=True)
class AppSpec:
    identity: AppIdentity
    display_name: str
    navigation: NavigationSpec
    check_in: CheckInSpec | None
    balance: BalanceSpec | None
    ad: AdSpec | None
    duration_reward: DurationRewardSpec | None
    content: ContentSpec | None
    withdrawal: WithdrawalSpec | None = None
    ad_entry: TargetSpec | None = None
    observation_profile: ObservationProfile = field(default_factory=ObservationProfile)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def content_kind(self) -> str:
        return str(getattr(self.content, "kind", ""))

    @property
    def video(self) -> VideoContentSpec | None:
        return self.content if isinstance(self.content, VideoContentSpec) else None

    @property
    def news(self) -> NewsContentSpec | None:
        return self.content if isinstance(self.content, NewsContentSpec) else None

    @property
    def audio(self) -> AudioContentSpec | None:
        return self.content if isinstance(self.content, AudioContentSpec) else None


def iter_target_specs(value: Any) -> tuple[TargetSpec, ...]:
    """递归收集规格里的业务目标，用于校验稳定的 target_id。"""

    targets: list[TargetSpec] = []
    visited: set[int] = set()

    def visit(item: Any) -> None:
        if isinstance(item, TargetSpec):
            targets.append(item)
            return
        item_id = id(item)
        if item_id in visited:
            return
        if is_dataclass(item) and not isinstance(item, type):
            visited.add(item_id)
            for item_field in fields(item):
                visit(getattr(item, item_field.name))
            return
        if isinstance(item, Mapping):
            visited.add(item_id)
            for nested in item.values():
                visit(nested)
            return
        if isinstance(item, (tuple, list, set, frozenset)):
            visited.add(item_id)
            for nested in item:
                visit(nested)

    visit(value)
    return tuple(targets)
