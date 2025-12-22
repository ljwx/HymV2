from abc import abstractmethod
from time import sleep

from apprun.appbase.data.ViewFlagsData import MainTaskPageData
from apprun.appbase.lv.AppRunLv1GoMainHome import AppRunLv1GoHome
from apppackage.AppPackage import AppPackageInfo
from device.DeviceManager import DeviceManager


class AppRunLv2GoTask(AppRunLv1GoHome):
    def __init__(self, app_info: AppPackageInfo, device: DeviceManager):
        super().__init__(app_info, device)

    def go_task_page(self) -> bool:
        self.logd("开始去任务页")
        if self._skip_home_and_task_page:
            self.logd("跳过","直接返回true")
            return True
        flag = self.get_task_page_flag()
        if flag.first_go_main_page:
            self.go_main_home_page()
        if self.device.flag_is_find_info(flag.task_page_enter_flag):
            self.logd("通过查找info")
            if self.device.click_by_flag(flag.task_page_enter_flag, 1):
                sleep(4)
        elif self.device.flag_is_image(flag.task_page_enter_flag):
            self.logd("通过image")
            if self.device.click_by_flag(flag.task_page_enter_flag, 1):
                sleep(4)
        else:
            self.logd("通过text")
            selected = self.device.is_text_selected(flag.task_page_enter_flag)
            if selected or self.device.click_by_flag(flag.task_page_enter_flag):
                sleep(4)
        for ad in flag.task_page_ad_flag:
            self.logd("关闭广告")
            self.device.click_by_flag(ad, 1)
        if self.device.exist_by_flag(flag.task_page_success_flag, 2):
            self.logd("去任务页成功")
            return True
        self.logd("去任务页失败")
        return False

    @abstractmethod
    def get_task_page_flag(self) -> MainTaskPageData:
        ...