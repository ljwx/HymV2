class UITargetInfo:
    def __init__(self, ui_name: str, size: tuple[float, float] | None = None,
                 position: tuple[float, float] | None = None,
                 text: str = None,
                 parent_name: str = None):
        self.ui_name = ui_name
        self.size = size
        self.position = position
        self.text = text
        self.parent_name = parent_name
