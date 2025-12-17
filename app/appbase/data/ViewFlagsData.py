import dataclasses

from device.uiview.FindUIInfo import FindUITargetInfo


@dataclasses.dataclass
class AppLaunchDialogData:
    close_flags: list[str]


@dataclasses.dataclass
class MainHomePageData:
    main_home_page_flag: str
    main_home_tab_flag: str
    main_home_page_intercept_flag: list[str] | None


@dataclasses.dataclass
class MainTaskPageData:
    first_go_home: bool
    task_tab_flag: str | FindUITargetInfo
    task_page_flag: str | FindUITargetInfo
    task_page_ad_flag: list[str | FindUITargetInfo] | None


@dataclasses.dataclass
class MainTaskHumanData:
    star_flag: str | None | FindUITargetInfo = None
    comment_flag: str | None | FindUITargetInfo = None
    go_works_flag: str | None | FindUITargetInfo = None
    works_success_flag: str | None | FindUITargetInfo = None
    works_list_flag: str | None | FindUITargetInfo = None


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
    next_ad_flag: list[str | FindUITargetInfo] | None
    close_flag: list[str | FindUITargetInfo]
    final_close_flag: list[str | FindUITargetInfo] | None


@dataclasses.dataclass
class DurationRewardData:
    is_go_task_page: bool
    reward_flag: str | FindUITargetInfo
    success_flag: str | FindUITargetInfo
    go_ad_flag: str | FindUITargetInfo | None
    close_flag: str | FindUITargetInfo
