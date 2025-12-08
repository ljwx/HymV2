from time import sleep

from app.kuaishou.Kuaishou import KuaiShouApp
from device.DeviceInfo import Mi15, HwP40
from device.DeviceManager import DeviceManager


class AppLaunch:

    def __init__(self):
        self.device = DeviceManager(Mi15())
        self.device.init_status()
        for app in self.get_apps():
            try:
                app.launch_app()
            except Exception as e:
                print(e)

    def clean_dialog(self):
        sleep(3)
        self.device.press_back()
        sleep(4)
        self.device.press_back()

    def test(self):
        self.device.exist_by_image(image_path="test/kn_test.png")

    def get_apps(self):
        return [KuaiShouApp(device=self.device)]
