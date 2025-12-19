from app.appbase.AppRunCommon import AppRunCommon
from app.appbase.data.ViewFlagsData import GoAnotherPageData
from apppackage.AppPackage import AppPackageInfo
from device.DeviceManager import DeviceManager


class AppRunLvCommon(AppRunCommon):
    def __init__(self, app_info: AppPackageInfo, device: DeviceManager):
        super().__init__(app_info, device)

    def _enter_another_page(self, data: GoAnotherPageData) -> bool:
        if self.device.click_by_flag(data.enter_another_page_flag):
            if self.device.exist_by_flag(data.another_page_success_flag, 8):
                return True
        return False
