from abc import ABC, abstractmethod
from time import sleep

from app.appbase.AppRunBase import AppRunBase
from apppackage.AppPackage import AppPackageInfo
from device.DeviceManager import DeviceManager


class AppRunCommon(AppRunBase):

    def __init__(self, app_info: AppPackageInfo, device: DeviceManager):
        super().__init__(app_info, device)

