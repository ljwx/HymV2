from typing import Callable, Any

from device.DeviceBase import DeviceInfo
from device.DeviceFindView import DeviceFindView


class DeviceCommonOperation(DeviceFindView):
    def __init__(self, device_info: DeviceInfo):
        super().__init__(device_info)

    def __dispatch_click(self, source: str) -> bool:
        if source.__contains__("/resource/"):
            return self.click_by_image(source)
        elif source.__contains__("com"):
            return self.click_by_id(source)
        else:
            if self.click_by_text(source):
                return True
            else:
                return self.click_by_desc(source, 1)

    def click_by_sequence(self, *args, on_fail: Callable[[], Any] | None = None) -> bool:
        for arg in args:
            print(arg)
            single = self.__dispatch_click(arg)
            if not single:
                if on_fail:
                    on_fail()
                return False
        return True

    def __example(self):
        self.click_by_sequence("更多设置", "时间和日期", "test", on_fail=lambda :(
            print(1),
            print(2)
        ))