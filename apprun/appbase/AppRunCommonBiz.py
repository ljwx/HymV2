import traceback
from abc import abstractmethod

from apprun.appbase.lv.othertask.AppRunOtherTask import AppRunOtherTask
from apppackage.AppPackage import AppPackageInfo
from device.DeviceManager import DeviceManager


class AppRunCommonBiz(AppRunOtherTask):
    def __init__(self, app_info: AppPackageInfo, device: DeviceManager):
        super().__init__(app_info, device)
