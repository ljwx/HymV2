from time import sleep

from app.AppRunProtocol import AppRunProtocol
from apppackage.AppPackage import PackageInfoKuaiShou
from device.DeviceManager import DeviceManager
from device.operation.UIOperation import UIOperation, Operation


class KuaiShouApp(AppRunProtocol):
    resource_dir = "kaishou/"
    close_icon = resource_dir + "task_tab_page_close_icon.png"

    def __init__(self, device: DeviceManager):
        self.device = device
        self.packageInfo = PackageInfoKuaiShou

    def launch_app(self) -> bool:
        try:
            # if not self.device.is_app_running(self.packageInfo.package_name):
            self.device.start_app(self.packageInfo.package_name)
            sleep(1)
            self.common_step()
            return True
        except Exception as e:
            print("启动异常", e)
            return False

    def common_step(self):
        self.handle_dialog()
        if self.is_home_page():
            self.go_task_page()

    def handle_dialog(self):
        # self.device.ui_operation_sequence(UIOperation(False, Operation.Exist_Click, "","限时大红包", "邀请新用户"))
        pass

    def is_home_page(self) -> bool:
        return self.device.exist_by_id("com.kuaishou.nebula:id/nasa_milano_progress_container") is not None

    def go_task_page(self) -> bool:
        if self.device.click_by_text("去赚钱"):
            sleep(4)
            ad1 = UIOperation(False, Operation.Exist_Click, self.close_icon, "瓜分百亿金币", 2)
            ad2 = UIOperation(False, Operation.Exist_Click, self.close_icon, "添加组件 金币领取不怕忘", 2)
            ad3 = UIOperation(False, Operation.Exist_Click, self.close_icon, "看内容领取金币", 2)
            ad4 = UIOperation(False, Operation.Exist_Click, self.close_icon, "去微信邀请好友", 2)
            self.device.ui_operation_sequence(ad1, ad2, ad3, ad4)
            self.sign_in()
            self.video_task()

    def sign_in(self) -> bool:
        # 签到
        if self.device.exist_by_text("今日签到可领"):  # 弹窗签到
            if self.device.click_by_text("立即签到"):
                sleep(2)
                if self.device.exist_by_text("明日签到可领"):
                    print("签到成功")
                    self.sign_in_after_task()
                    return True
        if self.device.click_by_text("立即签到", 2):  # 主动签到
            print("签到成功")
            return True
        return False

    def get_balance(self) -> str:
        return ""

    def sign_in_after_task(self):
        # 签到后的视频
        self.device.click_by_text("去看视频")
        if self.device.click_by_id("com.kuaishou.nebula.commercial_neo:id/video_countdown_end_icon", timeout=35):
            print("看视频完成")
            if self.device.click_by_text("领取额外金币"):
                self.device.click_by_text("拒绝", timeout=4)  # 打开其他app
                self.device.click_by_id("com.kuaishou.nebula.commercial_neo:id/video_countdown_end_icon", timeout=35)

    def loop_task(self):
        pass

    def video_task(self):
        if self.device.click_by_text("看广告得金币", 4):
            for i in range(0, 5):
                if self.video_item():
                    self.video_item()
        self.device.click_by_name("close_view", 5)

    def video_item(self) -> bool:
        # 单个视频任务
        if self.device.exist_by_id("com.kuaishou.nebula.commercial_neo:id/video_countdown"):
            self.device.sleep_task_random(30)
            self.device.click_by_id("com.kuaishou.nebula.commercial_neo:id/video_countdown_end_icon", timeout=35)
            self.device.sleep_operation_random()
            if self.device.exist_by_text("领取额外金币", 2):
                self.device.click_by_name("close_view", 1)
            if self.device.click_by_text("领取奖励", timeout=3):
                return True
        return False
