from abc import abstractmethod

from app.appbase.data.ViewFlagsData import AppLaunchDialogData
from app.appbase.lv.AppRunLv0Common import AppRunLvCommon
from apppackage.AppPackage import AppPackageInfo
from device.DeviceManager import DeviceManager


class AppRunLv0LaunchAd(AppRunLvCommon):
    def __init__(self, app_info: AppPackageInfo, device: DeviceManager):
        super().__init__(app_info, device)

    def handle_launch_dialog(self):
        for close_flag in self.get_handle_launch_dialog_flag().close_flags:
            self.device.click_by_flag(close_flag, 2)

    @abstractmethod
    def get_handle_launch_dialog_flag(self) -> AppLaunchDialogData:
        ...
