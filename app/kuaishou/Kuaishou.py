from time import sleep

from app.AppRunProtocol import AppRunProtocol
from apppackage.AppPackage import PackageInfoKuaiShou
from constant.Const import ConstViewType
from device.DeviceManager import DeviceManager
from device.operation.UIOperation import UIOperation, Operation
from device.uiview.UIInfo import UITargetInfo


class KuaiShouApp(AppRunProtocol):
    resource_dir = "kuaishou/"
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
        # if self.is_home_page():
        # if self.go_task_page():
        # self.check_in()
        # self.video_task()
        # self.get_balance()
        # self.get_consuming_reward()
        if self.is_home_page():
            self.main_task_range()

    def handle_dialog(self):
        # self.device.ui_operation_sequence(UIOperation(False, Operation.Exist_Click, "","限时大红包", "邀请新用户"))
        pass

    def is_home_page(self) -> bool:
        return self.device.exist_by_id("com.kuaishou.nebula:id/bottom_bar_container") is not None

    def go_task_page(self) -> bool:
        if self.device.click_by_text("去赚钱"):
            sleep(4)
            ad1 = UIOperation(False, Operation.Exist_Click, self.close_icon, "瓜分百亿金币", 2)
            ad2 = UIOperation(False, Operation.Exist_Click, self.close_icon, "添加组件 金币领取不怕忘", 2)
            ad3 = UIOperation(False, Operation.Exist_Click, self.close_icon, "看内容领取金币", 2)
            ad4 = UIOperation(False, Operation.Exist_Click, self.close_icon, "去微信邀请好友", 2)
            return self.device.ui_operation_sequence(ad1, ad2, ad3, ad4)
        return False

    def check_in(self) -> bool:
        # 签到
        exist_click = UIOperation(True, Operation.Exist_Click_Double, "立即签到", "今日签到可领")
        check_in_result = UIOperation(True, Operation.Exist, "明日签到可领", )
        if self.device.ui_operation_sequence(exist_click, check_in_result):
            print("签到成功")
            return True
        standby_check_in = UIOperation(True, Operation.Click, "立即签到", exist_timeout=2)
        if self.device.ui_operation_sequence(standby_check_in):
            print("签到成功")
            return True
        return False

    def get_balance(self) -> str:
        go_coin = UIOperation(True, Operation.Click, "我的金币")
        go_success = UIOperation(True, Operation.Exist, "我的收益")
        if self.device.ui_operation_sequence(go_coin, go_success):
            ui = self.device.find_ui_by_info(
                UITargetInfo(ConstViewType.Text, size=(0.23, 0.0486), position=(0.1908, 0.1898)))
            if ui and ui.get_text():
                print("获取的余额", ui.get_text())
                return ui.get_text()
        return ""

    def sign_in_after_task(self):
        # 签到后的视频
        self.device.click_by_text("去看视频")
        if self.device.click_by_id("com.kuaishou.nebula.commercial_neo:id/video_countdown_end_icon", timeout=35):
            print("看视频完成")
            if self.device.click_by_text("领取额外金币"):
                self.device.click_by_text("拒绝", timeout=4)  # 打开其他app
                self.device.click_by_id("com.kuaishou.nebula.commercial_neo:id/video_countdown_end_icon", timeout=35)

    def main_task_range(self):
        self.device.task_operation.main_task_range(callback=lambda: (
            self.main_task_item()
        ))

    def main_task_item(self):
        exist = UIOperation(True, Operation.Exist, "com.kuaishou.nebula:id/like_element_click_layout", exist_timeout=4)
        wait = UIOperation(True, Operation.Wait, "", )
        swipe = UIOperation(True, Operation.Swipe_Up_Mid, "",
                            exist_timeout=self.device.task_operation.get_main_task_duration())
        if self.device.ui_operation_sequence(exist):
            self.device.ui_operation_sequence(wait, swipe)

    def video_task(self):
        start_ad = UIOperation(True, Operation.Click, "看广告得金币", exist_timeout=4)
        if self.device.ui_operation_sequence(start_ad):
            for i in range(0, 5):
                if self.video_task_item():
                    self.video_task_item()
        self.device.click_by_name("close_view", 5)

    def video_task_item(self) -> bool:
        # 单个视频任务
        exist_waite_click = UIOperation(
            True, Operation.Exist_Wait_Click,
            "com.kuaishou.nebula.commercial_neo:id/video_countdown_end_icon",
            "com.kuaishou.nebula.commercial_neo:id/video_countdown", exist_timeout=30)
        extra_video_click = UIOperation(False, Operation.Click, "领取额外金币", exist_timeout=3)
        close_video_page = UIOperation(False, Operation.Click, "close_view", exist_timeout=2)
        receive_reward = UIOperation(True, Operation.Click, "领取奖励", exist_timeout=3)
        result = self.device.ui_operation_sequence(exist_waite_click, extra_video_click, close_video_page,
                                                   receive_reward)
        return result

    def get_consuming_reward(self):
        ui_trigger = self.device.find_all_contain_text(ConstViewType.Button, "点可领", timeout=5)
        if True or ui_trigger and ui_trigger.click():
            ad = self.device.find_all_contain_text(ConstViewType.Button, "去看广告得最高", timeout=5)
            if ad and ad.click():
                self.video_task_item()
            self.device.click_by_id("com.kuaishou.nebula.live_audience_plugin:id/live_close_place_holder")  # 直播
