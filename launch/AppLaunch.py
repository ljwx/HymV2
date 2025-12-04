from time import sleep

from apppackage.AppPackage import AppPackageInfo, TestApp
from device.DeviceInfo import Mi15, HwP40
from device.DeviceManager import DeviceManager


class AppLaunch:
    device: DeviceManager = DeviceManager(HwP40())
    packageInfo: AppPackageInfo = TestApp

    def __init__(self):
        self.device.init_status()
        # self.launchApp()
        self.test()

    def launchApp(self):
        if not self.device.is_app_running(self.packageInfo.package_name):
            self.device.start_app(self.packageInfo.package_name)

    def clean_dialog(self):
        sleep(3)
        self.device.press_back()
        sleep(4)
        self.device.press_back()

    def is_content_page(self):
        return self.device.exist_by_id("com.kuaishou.nebula:id/nasa_milano_progress_container") is not None

    def go_task_tab(self):
        self.device.click_by_id()

    def sign_in(self):
        if self.device.exist_by_id("今日签到可领"):
            if self.device.click_by_id("立即签到"):
                sleep(2)
                if self.device.exist_by_text("明日签到可领"):
                    print("签到成功")
                    self.sign_in_after_task()


    def sign_in_after_task(self):
        self.device.click_by_text("去看视频")
        if self.device.click_by_id("com.kuaishou.nebula.commercial_neo:id/video_countdown_end_icon", timeout=35):
            print("看视频完成")
            if self.device.click_by_text("领取额外金币"):
                self.device.click_by_text("拒绝", timeout=4) #打开其他app
                self.device.click_by_id("com.kuaishou.nebula.commercial_neo:id/video_countdown_end_icon", timeout=35)


    def test(self):
        self.device.exist_by_image(image_path="test/kn_test.png")