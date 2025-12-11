import traceback
from time import sleep
from typing import Callable, Any

from app.kuaishou.KuaiShouApp import KuaiShouApp
from device.DeviceInfo import Mi15, HwP40
from device.DeviceManager import DeviceManager


class AppLaunch:

    def __init__(self, callback: Callable[[DeviceManager, KuaiShouApp], Any] | None = None):
        self.device = DeviceManager(Mi15())
        self.device.init_status()
        for app in self.get_apps():
            try:
                if callback:
                    callback(self.device, app)
                else:
                    app.launch_app()
            except Exception as e:
                print("运行异常", e)
                traceback.print_exc()

    def clean_dialog(self):
        sleep(3)
        self.device.press_back()
        sleep(4)
        self.device.press_back()

    def test(self):
        self.device.exist_by_image(image_path="test/kn_test.png")

    def get_apps(self):
        return [KuaiShouApp(device=self.device)]
