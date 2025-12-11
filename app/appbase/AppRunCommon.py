import random
from abc import ABC, abstractmethod
from time import sleep

from app.appbase.AppRunBase import AppRunBase
from apppackage.AppPackage import AppPackageInfo
from device.DeviceManager import DeviceManager
from device.operation.UIOperation import UIOperation, Operation


class AppRunCommon(AppRunBase):
    main_home_page_flag: str
    main_task_tab_flag: str
    main_home_page_intercept_flag: list[str] | None

    star_flag: str | None = None
    comment_flag: str | None = None
    go_works_flag: str | None = None
    works_success_flag: str | None = None
    works_list_flag: str | None = None

    def __init__(self, app_info: AppPackageInfo, device: DeviceManager):
        super().__init__(app_info, device)

    def go_main_home_page(self, select_tab: bool = False) -> bool:
        for i in range(7):
            if self.main_home_page_intercept_flag is not None:
                for flag in self.main_home_page_intercept_flag:
                    self.device.click_by_flag(flag, 1)
            if self.device.exist_by_flag(self.main_home_page_flag, 4):
                if select_tab:
                    return self.device.click_by_flag(self.main_task_tab_flag, 2)
                return True
            else:
                sleep(5)
                self.device.press_back()
        return False

    def main_task_human(self, star: bool, comment: bool, works: bool):
        go_works_list = UIOperation(True, Operation.Click, self.go_works_flag)
        works_list_success = UIOperation(True, Operation.Exist, self.works_success_flag)
        if star and self.star_flag:
            self.device.click_by_flag(self.star_flag)
        if comment and self.comment_flag:
            self.device.click_by_flag(self.comment_flag)
        if works and self.go_works_flag:
            if self.device.ui_operation_sequence(go_works_list, works_list_success):
                for i in range(random.randint(1, 5)):
                    item = self.device.find_list_by_child(self.works_list_flag)
                    if item:
                        item.click()
                        self.main_task_item()
                        self.device.press_back()
                    self.device.swipe_up()
                    sleep(self.device.get_click_wait_time())
                sleep(self.device.get_click_wait_time())
                self.device.press_back()
