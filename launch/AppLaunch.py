from apppackage.AppPackage import AppPackageInfo, TestApp
from device.DeviceConnect import DeviceConnect, DeviceInfo
from device.DeviceManager import DeviceManager


class AppLaunch:

    device:DeviceManager = DeviceManager(DeviceInfo("NAB0220416035468"))
    packageInfo:AppPackageInfo = TestApp

    def __init__(self):
        self.launchApp()

    def launchApp(self):
        # if not self.device.is_app_running(self.packageInfo.package_name):
        #     self.device.start_app(self.packageInfo.package_name)

        # self.device.click_by_id("com.kuaishou.nebula:id/positive")
        self.device.click_by_desc("我")


AppLaunch()