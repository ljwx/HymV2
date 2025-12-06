from enum import auto, StrEnum


class Operation(StrEnum):
    Click = "click"
    Exist = "exist"
    Back = "back"
    Exist_Click = "exist_click"


class UIOperation:
    def __init__(self, must_success: bool, operation: Operation, ui_tag: str, exist_tag: str = None, timeout=8,
                 desc=None):
        self.operation = operation
        self.ui_tag = ui_tag
        self.exist_tag = exist_tag
        self.must_success = must_success
        self.timeout = timeout
