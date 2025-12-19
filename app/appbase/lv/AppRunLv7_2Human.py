from app.appbase.lv.AppRunLv7_1Duration import AppRunLv7_1Duration
from apppackage.AppPackage import AppPackageInfo
from device.DeviceManager import DeviceManager


class AppRunLv7_2Human(AppRunLv7_1Duration):
    def __init__(self, app_info: AppPackageInfo, device: DeviceManager):
        super().__init__(app_info, device)
