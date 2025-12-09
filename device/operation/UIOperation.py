from enum import auto, StrEnum


class Operation(StrEnum):
    Click = "click"
    Click_Double = "click_double"
    Exist = "exist"
    Back = "back"
    Exist_Click = "exist_click"
    Exist_Click_Double = "exist_click_duble"
    Exist_Wait_Click = "exist_wait_click"


class UIOperation:
    def __init__(self, must_success: bool, operation: Operation, operation_ui_flag: str, sub_exist_flag: str = None,
                 exist_timeout=8,
                 exist_waite_time=None,
                 desc=None):
        self.operation = operation
        self.operation_ui_flag = operation_ui_flag
        self.sub_exist_flag = sub_exist_flag
        self.must_success = must_success
        self.exist_timeout = exist_timeout
        self.exist_waite_time = exist_waite_time
