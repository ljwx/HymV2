from datetime import datetime


class Log:
    filter = "hym_run"

    VIEW_EXISTS = "view_exists"
    VIEW_CLICK = "view_click"
    SWIPE = "swipe"

    @classmethod
    def i(cls, tag: str, content: str):
        now = datetime.now()
        formatted_time = now.strftime("%Y-%m-%d %H:%M:%S")
        print(Log.filter, formatted_time, tag, content)

    @classmethod
    def d(cls, tag: str, content: str):
        now = datetime.now()
        formatted_time = now.strftime("%Y-%m-%d %H:%M:%S")
        print(Log.filter, formatted_time, tag, content)

    @classmethod
    def e(cls, tag: str, content: str):
        now = datetime.now()
        formatted_time = now.strftime("%Y-%m-%d %H:%M:%S")
        print(Log.filter, formatted_time, tag, content)

    @classmethod
    def d_view_exists(cls, content: str):
        cls.d(cls.VIEW_EXISTS, content)

    @classmethod
    def d_view_click(cls, content: str):
        cls.d(cls.VIEW_CLICK, content)

    @classmethod
    def d_swipe(cls, content: str):
        cls.d(cls.SWIPE, content)
