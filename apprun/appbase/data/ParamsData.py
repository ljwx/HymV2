import dataclasses

from device.uiview.FindUIInfo import FindUITargetInfo


@dataclasses.dataclass
class GoAnotherPageData:
    need_enter_another_page: bool = True
    enter_another_page_flag: str | FindUITargetInfo | None = None
    another_page_success_flag: str | FindUITargetInfo | None = None


@dataclasses.dataclass
class IsGoTaskPageData:
    is_go_task_page: bool
    first_close_ad_flag: bool


@dataclasses.dataclass
class CloseDialogData:
    common_dialog_flag: list[str | FindUITargetInfo] | None = None
    home_page_dialog_flags: list[str | FindUITargetInfo] | None = None
    task_page_dialog_flags: list[str | FindUITargetInfo] | None = None
    task_page_skip_close_dialog_flags: list[str | FindUITargetInfo] | None = None
