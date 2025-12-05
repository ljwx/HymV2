from time import sleep

from app.AppRunProtocol import AppRunProtocol
from apppackage.AppPackage import PackageInfoKuaiShou
from device.DeviceManager import DeviceManager


class KuaiShouApp(AppRunProtocol):

    def __init__(self, device: DeviceManager):
        self.device = device
        self.packageInfo = PackageInfoKuaiShou

    def launch_app(self) -> bool:
        try:
            # if not self.device.is_app_running(self.packageInfo.package_name):
            self.device.start_app(self.packageInfo.package_name)
            return True
        except Exception as e:
            print("启动异常", e)
            return False

    def common_step(self):
        self.handle_dialog()
        if self.is_home_page():
            self.go_task_page()

    def handle_dialog(self):
        pass

    def is_home_page(self) -> bool:
        return self.device.exist_by_id("com.kuaishou.nebula:id/nasa_milano_progress_container") is not None

    def go_task_page(self) -> bool:
        if self.device.click_by_sequence("去赚钱", ""):
            pass

    def sign_in(self) -> bool:
        if self.device.exist_by_id("今日签到可领"):
            if self.device.click_by_id("立即签到"):
                sleep(2)
                if self.device.exist_by_text("明日签到可领"):
                    print("签到成功")
                    self.sign_in_after_task()
        return False

    def get_balance(self) -> str:
        return ""

    def sign_in_after_task(self):
        self.device.click_by_text("去看视频")
        if self.device.click_by_id("com.kuaishou.nebula.commercial_neo:id/video_countdown_end_icon", timeout=35):
            print("看视频完成")
            if self.device.click_by_text("领取额外金币"):
                self.device.click_by_text("拒绝", timeout=4)  # 打开其他app
                self.device.click_by_id("com.kuaishou.nebula.commercial_neo:id/video_countdown_end_icon", timeout=35)

    def loop_task(self):
        pass