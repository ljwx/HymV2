import asyncio
import random
from time import sleep

from app.appbase.AppRunCommon import AppRunCommon
from app.appbase.data.ViewFlagsData import MainHomePageData, MainTaskPageData, MainTaskHumanData, AppLaunchDialogData
from apppackage.AppPackage import AppInfoKuaiShou
from constant.Const import ConstViewType, ConstFlag
from device.DeviceManager import DeviceManager
from device.operation.UIOperation import UIOperation, Operation
from device.uiview.FindUIInfo import FindUITargetInfo


class KuaiShouApp(AppRunCommon):
    app_info = AppInfoKuaiShou
    id_prefix = app_info.id_prefix
    ad_id_prefix = app_info.ad_id_prefix

    def __init__(self, device: DeviceManager):
        self.device = device
        super().__init__(self.app_info, device)
        self.resource_dir = "kuaishou/"
        self.close_icon = self.resource_dir + "task_tab_page_close_icon.png"
        self.check_in_icon = self.resource_dir + "check_in_icon.png"

    def handle_launch_dialog(self):
        super().handle_launch_dialog()
        if self.device.exist_by_text("邀请2个新用户必得"):
            close_icon = self.device.exist_by_find_info(
                FindUITargetInfo(ConstViewType.Image, (0.0758, 0.0340), (0.5, 0.7003)))
            if close_icon is not None:
                close_icon.click(focus=self.device.get_click_position_offset())
        # if self.device.exist_by_flag("朋友推荐", 1):
        #     self.device.click_by_flag("com.kuaishou.nebula:id/close_btn", 2)
        # self.device.ui_operation_sequence(UIOperation(False, Operation.Exist_Click, "","限时大红包", "邀请新用户"))
        pass

    def get_handle_launch_dialog_flag(self) -> AppLaunchDialogData:
        return AppLaunchDialogData([self.id_prefix + "close_btn"])

    def get_main_home_page_flag(self) -> MainHomePageData:
        return MainHomePageData(self.id_prefix + "bottom_bar_container", "首页", None)

    def get_task_page_flag(self) -> MainTaskPageData:
        return MainTaskPageData(True, "去赚钱", "任务中心", [self.close_icon, self.close_icon])

    # def go_task_page(self) -> bool:
    #     self.go_main_home_page()
    #     tab_flag = "去赚钱"
    #     selected = self.device.is_text_selected(tab_flag)
    #     if selected or self.device.click_by_text(tab_flag):
    #         sleep(4)
    #         ad1 = UIOperation(False, Operation.Exist_Click, self.close_icon, "瓜分百亿金币", 2)
    #         ad2 = UIOperation(False, Operation.Exist_Click, self.close_icon, "添加组件 金币领取不怕忘", 1)
    #         ad3 = UIOperation(False, Operation.Exist_Click, self.close_icon, "看内容领取金币", 1)
    #         ad4 = UIOperation(False, Operation.Exist_Click, self.close_icon, "去微信邀请好友", 1)
    #         exist = UIOperation(True, Operation.Exist, "任务中心", exist_timeout=4)
    #         return self.device.ui_operation_sequence(ad1, ad2, ad3, ad4, exist)
    #     return False

    def execute_check_in(self) -> bool:
        exist_click = UIOperation(True, Operation.Exist_Click, self.check_in_icon, "今日签到可领")
        check_in_result = UIOperation(True, Operation.Exist, "明日签到可领", )
        result = False
        if self.device.ui_operation_sequence(exist_click, check_in_result):
            result = True
        standby_check_in = UIOperation(True, Operation.Click, "立即签到", exist_timeout=2)
        if not result and self.device.ui_operation_sequence(standby_check_in):
            result = True
        if self.device.click_by_text("去看视频"):
            self.reward_ad_video_item()
        self.device.click_by_image(self.close_icon, timeout=2)
        return result

    def execute_get_balance(self) -> str | None:
        go_coin = UIOperation(True, Operation.Click, "我的金币")
        go_success = UIOperation(True, Operation.Exist, "我的收益")
        balance = None
        if self.device.ui_operation_sequence(go_coin, go_success):
            ui = self.device.exist_by_find_info(
                FindUITargetInfo(ConstViewType.Text, size=(0.23, 0.0486), position=(0.1908, 0.1898)))
            if ui is not None and ui.get_text():
                balance = ui.get_text()
            self.device.press_back()
        return balance

    def main_task_item(self):
        shopping_ad_video = self.id_prefix + "ad_download_progress"
        ask_ad_video = "咨询"
        ad_follow_flag = self.id_prefix + "slide_play_right_link_icon"
        live_video_text = "点击进入直播间"
        ads = [shopping_ad_video, ask_ad_video, ad_follow_flag]
        nors = [self.id_prefix + "create_date_tv", "全屏观看", "作者声明：演绎情节，仅供娱乐",
                self.id_prefix + "general_entry_single_root_view",
                self.id_prefix + "pic_text"]
        lon = ["继续观看完整版", "完整版", "合集"]
        if not self.device.exist_by_flag(self.id_prefix + "follow_avatar_view", 1.5):
            self.logd("非正常item，下一个")
            self.device.swipe_up()
            self.device.sleep_operation_random()
        normal, duration = asyncio.run(self.get_main_task_item_duration(ad_flag=ads, normal=nors, long_flag=lon))
        if normal and random.random() < 0.011:
            self.device.click_by_flag(self.id_prefix + "follow_button", 1)
        if self.device.exist_by_flag(self.id_prefix + "follow_avatar_view", 2):
            wait = UIOperation(True, Operation.Wait, "", exist_waite_time=duration)
            self.device.ui_operation_sequence(wait)
        else:
            self.device.swipe_up()
        return normal

    def get_main_human_flag(self) -> MainTaskHumanData:
        return MainTaskHumanData(
            self.id_prefix + "like_icon", self.id_prefix + "comment_icon",
            self.id_prefix + "user_name_text_view", self.id_prefix + "profile_user_kwai_id",
            self.id_prefix + "recycler_view")

    def start_video_task(self):
        video_ad_enter = "看广告得金币"

        def execute():
            self.reward_ad_video_item()
            sleep(self.device.get_click_wait_time())

        if self.go_task_page():
            if self.device.click_by_flag(video_ad_enter, 4):
                execute()
            else:
                self.device.swipe_up()
                if self.device.click_by_flag(video_ad_enter, 4):
                    execute()

    def reward_ad_video_item(self) -> bool:
        close_flag = self.ad_id_prefix + "video_countdown_end_icon"
        close_view = ConstFlag.Desc + "close_view"

        def first_video() -> bool:
            if self.device.exist_by_flag(self.ad_id_prefix + "video_countdown", 6):
                self.device.sleep_task_random(35)
                self.device.click_by_flag(close_flag)
                return True
            return False

        def second_video() -> bool:
            self.device.sleep_operation_random()
            if self.device.click_by_flag("领取奖励", 4):
                self.device.sleep_task_random(3)
                first_video()

        # 直播
        def live_video() -> bool:
            if self.device.exist_by_flag("com.kuaishou.nebula.live_audience_plugin:id/live_audience_bottom_mask_view",
                                         3):
                sleep(random.randint(16, 32))
                self.device.click_by_flag("com.kuaishou.nebula.live_audience_plugin:id/live_close_place_holder", 2)
                second_video()

        live_video()

        if first_video():
            second_video()
        if self.device.exist_by_flag("领取额外金币", 1):  # 打开app
            self.device.click_by_flag(close_view)
        self.device.click_by_flag(self.close_icon, timeout=1)
        if self.device.exist_by_flag("领取额外金币", 1):  # 打开app
            self.device.click_by_flag(close_view, 1)
        self.device.click_by_flag(close_view, 1)
        self.device.click_by_flag("com.kuaishou.nebula.live_audience_plugin:id/live_close_place_holder", 1)
        self.device.click_by_flag(close_view, 1)
        self.device.click_by_flag("退出直播间", 1)
        return True

    def get_duration_reward(self) -> bool:
        if not self.go_task_page():
            return False
        trigger1 = self.device.find_all_contain_text(ConstViewType.Text, "金币立即领取", timeout=3)
        if trigger1 is not None:
            trigger1.click(focus=self.device.get_click_position_offset())
            if self.device.exist_by_flag("任务完成奖励"):
                self.device.click_by_flag(self.close_icon, timeout=2)
        ui_trigger = self.device.find_all_contain_text(ConstViewType.Button, "点可领", timeout=2)
        if ui_trigger is not None:
            ui_trigger.click(focus=self.device.get_click_position_offset())
            sleep(3)
            if random.random() < 0.5:
                ad = self.device.find_all_contain_text(ConstViewType.Button, "去看广告得最高", timeout=5)
                if ad is not None:
                    ad.click(focus=self.device.get_click_position_offset())
                    self.reward_ad_video_item()
                    self.device.click_by_id("com.kuaishou.nebula.live_audience_plugin:id/live_close_place_holder",
                                            4)  # 直播
            else:
                self.device.click_by_image(self.close_icon, timeout=2)
            return True
        return False

    def other_reward_task1(self) -> bool:
        go = self.device.click_by_flag("到饭点领饭补", timeout=3)
        if go:
            if self.device.click_by_flag("看广告", 4):
                self.reward_ad_video_item()

            if self.device.click_by_flag("看广告领饭补", 3):
                self.reward_ad_video_item()
                self.device.press_back()

    def every_time_clear(self):
        pass
