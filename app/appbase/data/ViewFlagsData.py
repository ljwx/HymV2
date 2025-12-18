import dataclasses

from device.uiview.FindUIInfo import FindUITargetInfo


@dataclasses.dataclass
class GoAnotherPageData:
    need_enter_another_page: bool = True
    enter_another_page_flag: str | FindUITargetInfo | None = None
    another_page_success_flag: str | FindUITargetInfo | None = None


@dataclasses.dataclass
class AppLaunchDialogData:
    close_flags: list[str]


@dataclasses.dataclass
class MainHomePageData:
    main_home_page_flag: str | FindUITargetInfo
    main_home_tab_flag: str | FindUITargetInfo
    main_home_page_intercept_flag: list[str | FindUITargetInfo] | None


@dataclasses.dataclass
class MainTaskPageData:
    first_go_main_page: bool
    task_page_enter_flag: str | FindUITargetInfo
    is_text_and_can_selected: bool
    task_page_ad_flag: list[str | FindUITargetInfo] | None
    task_page_success_flag: str | FindUITargetInfo


@dataclasses.dataclass
class MainTaskHumanData:
    star_flag: str | None | FindUITargetInfo = None
    comment_flag: str | None | FindUITargetInfo = None
    go_works_flag: str | None | FindUITargetInfo = None
    works_success_flag: str | None | FindUITargetInfo = None
    works_list_flag: str | None | FindUITargetInfo = None


@dataclasses.dataclass
class CheckInData:
    is_go_task_page: bool
    first_force_ad_flag: list[str | FindUITargetInfo] | None
    check_in_flag: list[str | FindUITargetInfo]
    success_flag: str | FindUITargetInfo
    go_ad_video_flag: str | None | FindUITargetInfo
    is_back_task: bool
    close_flag: str | FindUITargetInfo | None


@dataclasses.dataclass
class GetBalanceData:
    is_go_task_page: bool
    enter_another_page: GoAnotherPageData | None
    only_snapshot: bool
    snapshot_path: str | None
    balance_flag: str | FindUITargetInfo


@dataclasses.dataclass
class StartVideoTaskData:
    is_go_home_page: bool
    is_go_task_pag: bool
    enter_flag: str | FindUITargetInfo = None


@dataclasses.dataclass
class RewardVideoAdItemData:
    start_success_flag: list[str | FindUITargetInfo]
    wait_time_range: float
    continue_flag: list[str | FindUITargetInfo] | None
    next_ad_flag_sequence: list[str | FindUITargetInfo] | None
    close_flag: list[str | FindUITargetInfo]
    final_close_flag: list[str | FindUITargetInfo] | None


@dataclasses.dataclass
class DurationRewardData:
    is_go_task_page: bool
    reward_flag: str | FindUITargetInfo
    success_flag: str | FindUITargetInfo
    go_ad_flag: str | FindUITargetInfo | None
    close_flag: str | FindUITargetInfo
