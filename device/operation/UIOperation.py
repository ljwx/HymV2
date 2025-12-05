from enum import auto, StrEnum


class Operation(StrEnum):
    Click = "click"
    Exist = "exist"
    Back = "back"


class UIOperation:
    def __init__(self, must_success: bool, operation: Operation, ui_tag: str):
        self.operation = operation
        self.ui_tag = ui_tag
        self.must_success = must_success
