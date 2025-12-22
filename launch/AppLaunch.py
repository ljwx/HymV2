import random
import traceback
from time import sleep
from typing import Callable, Any

from apprun.douyin.DouYinApp import DouYinApp
from apprun.kuaishou.KuaiShouApp import KuaiShouApp
from device.DeviceInfo import Mi15, HwP40
from device.DeviceManager import DeviceManager
from logevent.Log import Log


class AppLaunch:

    def __init__(self, callback: Callable[[DeviceManager, KuaiShouApp], Any] | None = None):
        while (True):
            try:
                self.main_task(callback)
                Log.d("运行", "本次所有App任务结束")
                print("")
                print("")
                print("")
            except Exception as e:
                Log.d("未知异常", str(e))
                traceback.print_exc()
            sleep(60)

    def main_task(self, callback: Callable[[DeviceManager, KuaiShouApp], Any] | None = None):
        device = DeviceManager(Mi15())
        if not device.device_ready:
            Log.d("device", "设备异常")
            return
        device.init_status()
        for app in self.get_apps(device):
            try:
                if callback:
                    callback(device, app)
                else:
                    app.launch_app()
                    device.sleep_operation_random()
                    device.press_home()
                    if random.random() > 0.5:
                        device.sleep_operation_random()
                    device.stop_app(app.app_info.package_name)
            except Exception as e:
                print("app运行异常", e)
                traceback.print_exc()

    def get_apps(self, device: DeviceManager):
        # return [DouYinApp(device=device)]
        return [KuaiShouApp(device=device), DouYinApp(device=device)]
