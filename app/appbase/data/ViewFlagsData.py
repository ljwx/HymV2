import dataclasses


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
    task_tab_flag: str
    task_page_flag: str
    task_page_ad_flag: list[str] | None


@dataclasses.dataclass
class MainTaskHumanData:
    star_flag: str | None = None
    comment_flag: str | None = None
    go_works_flag: str | None = None
    works_success_flag: str | None = None
    works_list_flag: str | None = None
