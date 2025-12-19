from app.appbase.lv.AppRunLv7_2Human import AppRunLv7_2Human
from apppackage.AppPackage import AppPackageInfo
from device.DeviceManager import DeviceManager


class AppRunLv7MainTask(AppRunLv7_2Human):
    def __init__(self, app_info: AppPackageInfo, device: DeviceManager):
        super().__init__(app_info, device)
