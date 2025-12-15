import asyncio
import random
from time import sleep

from poco.proxy import UIObjectProxy

from app.appbase.AppRunCommon import AppRunCommon
from app.appbase.data.ViewFlagsData import MainHomePageData, MainTaskPageData, MainTaskHumanData, AppLaunchDialogData
from apppackage.AppPackage import AppInfoKuaiShou, AppInfoDouYin
from constant.Const import ConstViewType, ConstFlag
from device.DeviceManager import DeviceManager
from device.operation.UIOperation import UIOperation, Operation
from device.uiview.FindUIInfo import FindUITargetInfo


class DouYinApp(AppRunCommon):
    app_info = AppInfoDouYin
    id_prefix = app_info.id_prefix
    ad_id_prefix = app_info.ad_id_prefix

    def __init__(self, device: DeviceManager):
        self.device = device
        super().__init__(self.app_info, device)
        self.resource_dir = "douyin/"
        self.close_icon = self.resource_dir + "bg_white_close_icon.png"

    def handle_launch_dialog(self):
        super().handle_launch_dialog()
        pass

    def get_handle_launch_dialog_flag(self) -> AppLaunchDialogData:
        return AppLaunchDialogData([])

    def get_main_home_page_flag(self) -> MainHomePageData:
        return MainHomePageData(self.id_prefix + "root_view", "首页", None)

    def get_task_page_flag(self) -> MainTaskPageData:
        task_tab_icon = self.resource_dir + "main_task_tab.png"
        task_page_success = self.resource_dir + "task_page_success_icon.png"
        return MainTaskPageData(True, task_tab_icon, task_page_success, [self.close_icon])

    def execute_check_in(self) -> bool:
        result = False
        if self.device.click_by_flag(self.resource_dir + "check_in_btn.png"):
            result = True
            self.device.sleep_operation_random()
            self.device.click_by_flag(self.resource_dir + "check_in_success_close_icon.png")
        # standby_check_in = UIOperation(True, Operation.Click, "立即签到", exist_timeout=2)
        # if not result and self.device.ui_operation_sequence(standby_check_in):
        #     result = True
        # if self.device.click_by_text("去看视频"):
        #     self.reward_ad_video_item()
        # self.device.click_by_image(self.close_icon, timeout=2)
        return result

    def get_balance(self) -> str | None:
        go_coin = UIOperation(True, Operation.Click, "我的金币")
        go_success = UIOperation(True, Operation.Exist, "我的收益")
        balance = None
        if self.device.ui_operation_sequence(go_coin, go_success):
            ui = self.device.exist_by_find_info(
                FindUITargetInfo(ConstViewType.Text, size=(0.23, 0.0486), position=(0.1908, 0.1898)))
            if ui and ui.get_text():
                balance = ui.get_text()
            self.device.press_back()
        return balance

    def main_task_item(self):
        exist_flag = self.id_prefix + "user_avatar"
        ads = [ConstFlag.Desc + "当前直播间可用"]
        nors = [ConstFlag.Desc + "音乐，@🧊创作的原声，按钮", "全屏观看", "相关搜索", "拍同款"]
        lon = ["点击进入看全集", "听抖音"]
        if not self.device.exist_by_flag(exist_flag, 1.5):
            self.logd("非正常item，下一个")
            self.device.swipe_up()
            self.device.sleep_operation_random()
        normal, duration = asyncio.run(self.get_main_task_item_duration(ad_flag=ads, normal=nors, long_flag=lon))
        if normal and random.random() < 0.1:
            self.device.click_by_flag(self.resource_dir + "follow_user", 1)
        if self.device.exist_by_flag(exist_flag, 2):
            sleep(duration)
        else:
            self.device.swipe_up()
        return normal

    def get_main_human_flag(self) -> MainTaskHumanData:
        return MainTaskHumanData(
            ConstFlag.Position + "[0.9133, 0.4898]", ConstFlag.Position + "[0.9133, 0.5737]",
            self.id_prefix + "user_avatar", "获赞",
            ConstViewType.Recycler)

    def start_video_task(self):

        def find_enter() -> bool | None:
            first = self.device.find_all_contain_name(ConstViewType.Group, "每20分钟完成一次广告任务", 2)
            if first:
                first.click()
                return True
            second = self.device.find_all_contain_name(ConstViewType.Group, "看广告视频，", 2)
            if second:
                second.click()
                return True
            return False

        def execute():
            self.reward_ad_video_item()
            sleep(self.device.get_click_wait_time())

        if self.go_task_page():
            if find_enter():
                execute()
            else:
                self.device.swipe_up()
                if find_enter():
                    execute()

    def reward_ad_video_item(self) -> bool:
        self.device.click_by_flag(self.resource_dir + "duration_reward_close_icon.png", 1)

        def ad_page_back():
            self.device.click_by_flag(self.id_prefix + "iv_back", 1)

        def first_video() -> bool:
            if self.device.find_all_contain_name(ConstViewType.Group, "秒后可领奖励", 4):
                self.device.sleep_operation_random(random.randint(33, 39))
                ad_page_back()
                close_flag = self.device.find_all_contain_name(ConstViewType.Group, "领取成功，关闭，按钮", 4)
                if close_flag:
                    ad_page_back()
                    close_flag.click(focus=self.device.get_click_position_offset())
                    ad_page_back()
                    close_flag.click(focus=self.device.get_click_position_offset())
                ad_page_back()
            return False

        def second_video() -> bool:
            if self.device.click_by_flag(self.resource_dir + "video_ad_second_flag.png", 4):
                self.device.sleep_task_random(3)
                first_video()

        for i in range(2):
            first_video()
            second_video()
            self.device.click_by_flag(self.id_prefix + "iv_back", 1)
        self.device.click_by_flag(self.resource_dir + "close_video_ad_icon.png", 1)
        self.device.click_by_flag(self.resource_dir + "close_video_ad_icon.png", 1)
        return True

    def get_duration_reward(self) -> bool:
        if not self.go_task_page():
            return False
        close_icon = self.resource_dir + "duration_reward_close_icon.png"
        go_ad_enter = FindUITargetInfo(ConstViewType.Group, size=(0.5866, 0.0625), position=(0.5, 0.5535),
                                       z_orders={'global': 0, 'local': 3}, parent_name=ConstViewType.Group)
        if self.device.click_by_flag(ConstFlag.Desc + "开宝箱得金币", 2):
            self.device.click_by_flag(close_icon, 4)
            if self.device.click_by_find_info(go_ad_enter, 4):
                self.reward_ad_video_item()
            return True
        if self.device.click_by_flag(self.resource_dir + "duration_reward_icon.png", 1):
            self.device.click_by_flag(close_icon, 4)
            return True
        return False

    def every_time_clear(self):
        pass
