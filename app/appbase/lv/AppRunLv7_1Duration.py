from app.appbase.lv.AppRunLv6AdVideo import AppRunLv6AdVideo
from apppackage.AppPackage import AppPackageInfo
from device.DeviceManager import DeviceManager


class AppRunLv7_1Duration(AppRunLv6AdVideo):
    def __init__(self, app_info: AppPackageInfo, device: DeviceManager):
        super().__init__(app_info, device)
