from typing import Callable, Any

from poco.proxy import UIObjectProxy

from device.DeviceBase import DeviceInfo
from device.DeviceFindView import DeviceFindView
from device.operation.UIOperation import UIOperation, Operation


class DeviceCommonOperation(DeviceFindView):
    def __init__(self, device_info: DeviceInfo):
        super().__init__(device_info)

    def __dispatch_exist(self, source: str) -> UIObjectProxy | tuple[float, float] | None:
        if source.__contains__("/resource/"):
            return self.exist_by_image(source)
        elif source.__contains__("com"):
            return self.exist_by_id(source)
        else:
            for i in range(0, 4):
                tv = self.exist_by_text(source, 1)
                if tv:
                    return tv
                else:
                    decs = self.exist_by_desc(source, 1)
                    if decs:
                        return decs
        return None

    def __dispatch_click(self, source: str) -> bool:
        if source.__contains__("/resource/"):
            return self.click_by_image(source)
        elif source.__contains__("com"):
            return self.click_by_id(source)
        else:
            for i in range(0, 4):
                if self.click_by_text(source, 1):
                    return True
                else:
                    if self.click_by_desc(source, 1):
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
            result = self.__dispatch_click(ui.ui_tag)
        if op is Operation.Exist:
            result = self.__dispatch_exist(ui.ui_tag)
        if op is Operation.Exist_Click:
            exist = self.__dispatch_exist(ui.exist_tag)
            if exist:
                result = self.__dispatch_click(ui.ui_tag)
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
