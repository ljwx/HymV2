from app.appbase.AppRunCommonBiz import AppRunCommonBiz
from apppackage.AppPackage import AppPackageInfo
from device.DeviceManager import DeviceManager


class AppRunFather(AppRunCommonBiz):
    def __init__(self, app_info: AppPackageInfo, device: DeviceManager):
        super().__init__(app_info, device)
