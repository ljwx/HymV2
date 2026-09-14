from apprun.appbase.lv.AppRunLv7MainTask import AppRunLv7MainTask
from apppackage.AppPackage import AppPackageInfo
from device.DeviceManager import DeviceManager


class AppRunOtherTask(AppRunLv7MainTask):
    def __init__(self, app_info: AppPackageInfo, device: DeviceManager):
        super().__init__(app_info, device)
