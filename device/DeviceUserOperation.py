import random
from time import sleep
from typing import Callable, Any

from poco.proxy import UIObjectProxy

from device.DeviceBase import DeviceInfo
from device.DeviceFindView import DeviceFindView
from device.config.TaskRandomConfig import TaskRandomConfig
from device.operation.TaskOperation import TaskOperation
from device.operation.UIOperation import UIOperation, Operation


class DeviceCommonOperation(DeviceFindView):
    def __init__(self, device_info: DeviceInfo):
        super().__init__(device_info)
        self.task_operation = TaskOperation()

    def click_by_sequence(self, *args, on_fail: Callable[[], Any] | None = None) -> bool:
        for arg in args:
            print(arg)
            single = self.click_by_flag(arg)
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
            result = self.click_by_flag(ui.operation_ui_flag, ui.exist_timeout)
        if op is Operation.Random_Is_Click:
            if random.random() < 0.3:
                self.click_by_flag(ui.operation_ui_flag, ui.exist_timeout)
            result = True
        if op is Operation.Exist:
            result = self.exist_by_flag(ui.operation_ui_flag, ui.exist_timeout)
        if op is Operation.Exist_Click:
            exist = self.exist_by_flag(ui.sub_exist_flag, ui.exist_timeout)
            if exist:
                result = self.click_by_flag(ui.operation_ui_flag, ui.exist_timeout)
        if op is Operation.Exist_Wait_Click:
            exist = self.exist_by_flag(ui.sub_exist_flag, ui.exist_timeout)
            if exist:
                waite_time = 25 if ui.exist_waite_time is None else ui.exist_waite_time
                self.sleep_task_random(waite_time)
                result = self.click_by_flag(ui.operation_ui_flag, ui.exist_timeout)
        if op is Operation.Swipe_Up_Mid:
            self.swipe_up()
            result = True
        if op is Operation.Wait:
            waite_time = 25 if ui.exist_waite_time is None else ui.exist_waite_time
            self.sleep_task_random(waite_time)
            return True
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
