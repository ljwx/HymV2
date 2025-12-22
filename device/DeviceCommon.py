from poco.proxy import UIObjectProxy

from device.DeviceBase import DeviceBase
from device.DeviceInfo import DeviceInfo
from device.uiview.FindUIInfo import FindUITargetInfo


class DeviceCommon(DeviceBase):
    def __init__(self, device_info: DeviceInfo):
        super().__init__(device_info)

    def swipe_up_find_flag(self, times: int, flag: str | FindUITargetInfo, timeout=4) -> UIObjectProxy | None | tuple[
        float, float]:
        for i in range(times):
            flag = self.exist_by_flag(flag, timeout=timeout)
            if flag is not None:
                return flag
            self.swipe_up()
            self.sleep_operation_random()
        return None

    def exist_by_flags_or(self, flags: list[str | FindUITargetInfo],
                          timeout: float = 5) -> UIObjectProxy | None | tuple[float, float]:
        for flag in flags:
            result = self.exist_by_flag(flag, timeout=timeout)
            if result is not None:
                return result
        return None

    def click_by_flags_and(self, flags: list[str | FindUITargetInfo], timeout=5) -> bool:
        result = True
        for flag in flags:
            if not self.click_by_flag(flag, timeout=timeout):
                result = False
        return result

    def click_by_flags_or(self, flags: list[str | FindUITargetInfo], timeout=5) -> bool:
        result = False
        for flag in flags:
            if self.click_by_flag(flag, timeout=timeout):
                result = True
        return result
