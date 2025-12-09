from time import sleep
from typing import Callable, Any

from poco.proxy import UIObjectProxy

from device.DeviceBase import DeviceInfo
from device.DeviceFindView import DeviceFindView
from device.operation.UIOperation import UIOperation, Operation


class DeviceCommonOperation(DeviceFindView):
    def __init__(self, device_info: DeviceInfo):
        super().__init__(device_info)

    def __dispatch_exist(self, source: str, timeout: int) -> UIObjectProxy | tuple[float, float] | None:
        if source.lower().endswith(".png") or source.lower().endswith(".jpg") or source.lower().endswith(".jpeg"):
            return self.exist_by_image(source, timeout)
        elif source.__contains__("com"):
            return self.exist_by_id(source, timeout)
        else:
            for i in range(0, timeout):
                tv = self.exist_by_text(source, 0.5)
                if tv:
                    return tv
                else:
                    decs = self.exist_by_desc(source, 0.5)
                    if decs:
                        return decs
        return None

    def __dispatch_click(self, source: str, timeout: int, double_check: bool = False) -> bool:
        if source.__contains__("/resource/"):
            return self.click_by_image(source, timeout=timeout)
        elif source.__contains__("com"):
            return self.click_by_id(source, timeout, double_check)
        else:
            for i in range(0, timeout):
                if self.click_by_text(source, 0.5, double_check):
                    return True
                else:
                    if self.click_by_desc(source, 0.5, double_check):
                        return True
        return False

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
        self.click_by_sequence("更多设置", "时间和日期", "test", on_fail=lambda: (
            print(1),
            print(2)
        ))

    def __handle_operation(self, ui: UIOperation) -> bool:
        op = ui.operation
        result = True
        if op is Operation.Click:
            result = self.__dispatch_click(ui.operation_ui_flag, ui.exist_timeout)
        if op is Operation.Click_Double:
            result = self.__dispatch_click(ui.operation_ui_flag, ui.exist_timeout, True)
        if op is Operation.Exist:
            result = self.__dispatch_exist(ui.operation_ui_flag, ui.exist_timeout)
        if op is Operation.Exist_Click:
            exist = self.__dispatch_exist(ui.sub_exist_flag, ui.exist_timeout)
            if exist:
                result = self.__dispatch_click(ui.operation_ui_flag, ui.exist_timeout)
        if op is Operation.Exist_Wait_Click:
            exist = self.__dispatch_exist(ui.sub_exist_flag, ui.exist_timeout)
            if exist:
                waite_time = 25 if ui.exist_waite_time is None else ui.exist_waite_time
                self.sleep_task_random(waite_time)
                result = self.__dispatch_click(ui.operation_ui_flag, ui.exist_timeout)
        if op is Operation.Back:
            self.press_back()
            result = True
        if ui.must_success:
            return result
        return True

    def ui_operation_sequence(self, *args):
        for arg in args:
            if isinstance(arg, UIOperation):
                if not self.__handle_operation(arg):
                    return False
        return True

    def ui_operation_2d_array(self, list: list[list]) -> bool:
        for inner_list in list:
            if not self.ui_operation_sequence(*inner_list):
                return False
        return True
