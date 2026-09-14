import asyncio
import random
from abc import ABC, abstractmethod
from time import sleep

from apprun.appbase.AppRunBase import AppRunBase
from apprun.appbase.data.ViewFlagsData import MainHomePageData, MainTaskPageData, MainTaskHumanData, AppLaunchDialogData
from apppackage.AppPackage import AppPackageInfo
from device.DeviceManager import DeviceManager
from device.operation.UIOperation import UIOperation, Operation


class AppRunCommon(AppRunBase):
    COLOR_RED = '\033[91m'
    COLOR_GREEN = '\033[92m'
    COLOR_YELLOW = '\033[93m'
    COLOR_BLUE = '\033[94m'
    COLOR_RESET = '\033[0m'  # 重置颜色

    def __init__(self, app_info: AppPackageInfo, device: DeviceManager):
        super().__init__(app_info, device)
