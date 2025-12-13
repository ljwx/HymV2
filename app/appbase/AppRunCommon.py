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
        self.logd("去首页", "首页tab是否需要选中", select_tab)
        for i in range(5):
            if self.device.exist_by_flag(self.main_home_page_flag, 4):
                self.logd("成功回到首页")
                if select_tab:
                    return self.device.click_by_flag(self.main_task_tab_flag, 2)
                return True
            if self.main_home_page_intercept_flag is not None:
                for flag in self.main_home_page_intercept_flag:
                    self.device.click_by_flag(flag, 1)
            else:
                sleep(5)
                self.device.press_back()
        return False

    def get_main_task_item_duration(self, ad_flag: list[str], normal: list[str], long_flag: list[str]) -> tuple[
        bool, float]:
        duration = self.device.task_operation.get_main_task_duration_with_ad()
        result = (False, duration)
        for ad in ad_flag:
            if self.device.exist_by_flag(ad, 0.3):
                duration = self.device.task_operation.get_video_ad_duration(1)
                result = (False, duration)
                self.logd("当前主任务是广告", repr(ad), repr(duration))
                return result
        for nor in normal:
            if self.device.exist_by_flag(nor, 0.3):
                duration = self.device.task_operation.get_main_task_duration()
                result = (True, duration)
                self.logd("当前主任务是常规item", result)
                return result
        for lon in long_flag:
            if self.device.exist_by_flag(lon, 0.3):
                duration = self.device.task_operation.get_main_task_duration_with_movie()
                result = (True, duration)
                self.logd("当前主任务是长视频", result)
        return result

    def main_task_human(self, star: bool, comment: bool, works: bool):
        self.logd("===模拟常规操作===", star, comment, works)
        go_works_list = UIOperation(True, Operation.Click, self.go_works_flag)
        works_list_success = UIOperation(True, Operation.Exist, self.works_success_flag)
        if star and self.star_flag:
            self.logd("点赞")
            self.device.click_by_flag(self.star_flag)
            self.device.sleep_operation_random()
        if comment and self.comment_flag:
            self.logd("看评论")
            self.device.click_by_flag(self.comment_flag)
            self.device.sleep_operation_random(2)
            self.device.press_back()
            self.device.sleep_operation_random()
        if works and self.go_works_flag:
            self.logd("去作品列表")
            if self.device.ui_operation_sequence(go_works_list, works_list_success):
                for i in range(random.randint(1, 5)):
                    item = self.device.find_list_by_child(self.works_list_flag)
                    if item and item.exists():
                        try:
                            self.device.sleep_operation_random()
                            item.click()
                            self.main_task_item()
                            self.device.press_back()
                            self.device.sleep_operation_random()
                        except Exception as e:
                            self.logd("点击作品项失败，可能不在屏幕内", str(e))
                    self.device.swipe_up()
                    sleep(self.device.get_click_wait_time())
                sleep(self.device.get_click_wait_time())
                self.device.press_back()
        self.logd("===常规操作结束===", "\n")
