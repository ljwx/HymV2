import random
from abc import abstractmethod
from time import sleep

from app.appbase.data.ViewFlagsData import MainTaskHumanData
from app.appbase.lv.AppRunLv7_1Duration import AppRunLv7_1Duration
from apppackage.AppPackage import AppPackageInfo
from device.DeviceManager import DeviceManager
from device.operation.UIOperation import UIOperation, Operation


class AppRunLv7_2Human(AppRunLv7_1Duration):
    def __init__(self, app_info: AppPackageInfo, device: DeviceManager):
        super().__init__(app_info, device)

    def main_task_human(self, star: bool, comment: bool, works: bool):
        self.logd("===模拟常规操作===", star, comment, works)
        flag = self.get_main_human_flag()
        go_works_list = UIOperation(True, Operation.Click, flag.go_works_flag)
        works_list_success = UIOperation(True, Operation.Exist, flag.works_success_flag)
        if star and flag.star_flag:
            self.logd("点赞")
            self.device.click_by_flag(flag.star_flag)
            self.device.sleep_operation_random()
        if comment and flag.comment_flag:
            self.logd("看评论")
            self.device.click_by_flag(flag.comment_flag)
            self.device.sleep_operation_random(2)
            self.device.press_back()
            self.device.sleep_operation_random()
        if works and flag.go_works_flag:
            self.logd("去作品列表")
            if self.device.ui_operation_sequence(go_works_list, works_list_success):
                for i in range(random.randint(1, 5)):
                    item = self.device.find_list_by_child(flag.works_list_flag)
                    if item is not None and item.exists():
                        try:
                            self.device.sleep_operation_random()
                            item.click(focus=self.device.get_click_position_offset())
                            self.main_task_item()
                            self.device.press_back()
                            self.device.sleep_operation_random()
                        except Exception as e:
                            self.logd("点击作品项失败，可能不在屏幕内", str(e))
                    self.device.swipe_up()
                    sleep(self.device.get_click_wait_time())
                sleep(self.device.get_click_wait_time())
                self.device.press_back()
        self.logd("===常规操作结束===", "enter")

    @abstractmethod
    def get_main_human_flag(self) -> MainTaskHumanData:
        ...
