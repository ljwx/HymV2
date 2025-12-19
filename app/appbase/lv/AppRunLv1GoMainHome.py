from abc import abstractmethod
from time import sleep

from app.appbase.data.ViewFlagsData import MainHomePageData
from app.appbase.lv.AppRunLv0LaunchAd import AppRunLv0LaunchAd
from apppackage.AppPackage import AppPackageInfo
from device.DeviceManager import DeviceManager


class AppRunLv1GoHome(AppRunLv0LaunchAd):
    def __init__(self, app_info: AppPackageInfo, device: DeviceManager):
        super().__init__(app_info, device)

    def go_main_home_page(self, select_tab: bool = False) -> bool:
        self.logd("去首页", "首页tab是否需要选中", select_tab)
        if self._skip_home_and_task_page:
            self.logd("跳过","直接返回true")
            return True
        flags = self.get_main_home_page_flag()
        main_home_page_flag = flags.main_home_page_flag
        main_home_tab_flag = flags.main_home_tab_flag
        main_home_page_intercept_flag = flags.main_home_page_intercept_flag
        for i in range(5):
            if self.device.exist_by_flag(main_home_page_flag, 2):
                self.logd("成功回到首页")
                if select_tab:
                    if self.device.is_text_selected(main_home_tab_flag):
                        return True
                    return self.device.click_by_flag(main_home_tab_flag, 2)
                return True
            if main_home_page_intercept_flag is not None:
                for flag in main_home_page_intercept_flag:
                    self.device.click_by_flag(flag, 1)
            else:
                sleep(4)
                self.device.press_back()
        return False

    @abstractmethod
    def get_main_home_page_flag(self) -> MainHomePageData:
        ...