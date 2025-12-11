import random
from time import sleep

from app.appbase.AppRunCommon import AppRunCommon
from apppackage.AppPackage import AppInfoKuaiShou
from constant.Const import ConstViewType
from device.DeviceManager import DeviceManager
from device.operation.UIOperation import UIOperation, Operation
from device.uiview.UIInfo import UITargetInfo


class KuaiShouApp(AppRunCommon):
    app_info = AppInfoKuaiShou
    id_prefix = app_info.id_prefix
    ad_id_prefix = app_info.ad_id_prefix

    # 回首页
    main_home_page_flag = id_prefix + "bottom_bar_container"
    main_task_tab_flag = "首页"
    main_home_page_intercept_flag: list | None = None

    # 点赞
    star_flag = id_prefix + "like_icon"
    comment_flag = id_prefix + "comment_icon"
    go_works_flag = id_prefix + "follow_avatar_view"
    works_success_flag = id_prefix + "profile_user_kwai_id"
    works_list_flag = id_prefix + "recycler_view"

    def __init__(self, device: DeviceManager):
        self.device = device
        super().__init__(self.app_info, device)
        self.resource_dir = "kuaishou/"
        self.close_icon = self.resource_dir + "task_tab_page_close_icon.png"

    def handle_lunch_dialog(self):
        if self.device.exist_by_text("邀请2个新用户必得"):
            close_icon = self.device.find_ui_by_info(UITargetInfo(ConstViewType.Image, (0.0758, 0.0340), (0.5, 0.7003)))
            if close_icon:
                close_icon.click()
        if self.device.exist_by_flag("朋友推荐", 1):
            self.device.click_by_flag("com.kuaishou.nebula:id/close_btn", 2)
        # self.device.ui_operation_sequence(UIOperation(False, Operation.Exist_Click, "","限时大红包", "邀请新用户"))
        pass

    def go_task_page(self) -> bool:
        self.go_main_home_page()
        tab_flag = "去赚钱"
        selected = self.device.is_text_selected(tab_flag)
        if selected or self.device.click_by_text(tab_flag):
            sleep(4)
            ad1 = UIOperation(False, Operation.Exist_Click, self.close_icon, "瓜分百亿金币", 2)
            ad2 = UIOperation(False, Operation.Exist_Click, self.close_icon, "添加组件 金币领取不怕忘", 2)
            ad3 = UIOperation(False, Operation.Exist_Click, self.close_icon, "看内容领取金币", 2)
            ad4 = UIOperation(False, Operation.Exist_Click, self.close_icon, "去微信邀请好友", 2)
            exist = UIOperation(True, Operation.Exist, "任务中心", exist_timeout=4)
            return self.device.ui_operation_sequence(ad1, ad2, ad3, ad4, exist)
        return False

    def execute_check_in(self) -> bool:
        exist_click = UIOperation(True, Operation.Exist_Click, "今天", "今日签到可领")
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

    def get_balance(self) -> str | None:
        go_coin = UIOperation(True, Operation.Click, "我的金币")
        go_success = UIOperation(True, Operation.Exist, "我的收益")
        balance = None
        if self.device.ui_operation_sequence(go_coin, go_success):
            ui = self.device.find_ui_by_info(
                UITargetInfo(ConstViewType.Text, size=(0.23, 0.0486), position=(0.1908, 0.1898)))
            if ui and ui.get_text():
                balance = ui.get_text()
            self.device.press_back()
        return balance

    def main_task_item(self):
        exist = UIOperation(True, Operation.Exist, self.app_info.id_prefix + "like_element_click_layout",
                            exist_timeout=4)
        wait = UIOperation(True, Operation.Wait, "",
                           exist_waite_time=self.device.task_operation.get_main_task_duration())
        ad_wait = UIOperation(True, Operation.Wait, "",
                              exist_waite_time=self.device.task_operation.get_main_task_duration_with_ad())
        movie_wait = UIOperation(True, Operation.Wait, "",
                                 exist_waite_time=self.device.task_operation.get_main_task_duration_with_movie())
        swipe = UIOperation(True, Operation.Swipe_Up_Mid, "",
                            exist_timeout=self.device.task_operation.get_main_task_duration())
        shopping_ad_video = "com.kuaishou.nebula:id/ad_download_progress"
        ask_ad_video = "com.kuaishou.nebula:id/plc_tv_biz_text"
        live_video_text = "点击进入直播间"
        long_video1 = "继续观看完整版"
        long_video2 = "完整版"
        picture_vidoe = "长图"
        if self.device.ui_operation_sequence(exist):
            real_waite = wait
            if (self.device.exist_by_flag(shopping_ad_video, 1)
                    or self.device.exist_by_flag(ask_ad_video, 0.5)
                    or self.device.exist_by_flag(live_video_text, 0.5)):
                real_waite = ad_wait
            elif self.device.exist_by_flag(long_video1, 1) or self.device.exist_by_flag(long_video2, 1):
                real_waite = movie_wait
            self.device.ui_operation_sequence(real_waite, swipe)

    def start_video_task(self):
        video_ad_enter = "看广告得金币"

        def execute():
            self.reward_ad_video_item()
            sleep(self.device.get_click_wait_time())

        if self.go_task_page():
            if self.device.click_by_text(video_ad_enter, 4):
                execute()
            else:
                self.device.swipe_up()
                if self.device.click_by_text(video_ad_enter, 4):
                    execute()

    def reward_ad_video_item(self) -> bool:
        close_flag = self.ad_id_prefix + "video_countdown_end_icon"
        exist_waite_click = UIOperation(
            True, Operation.Exist_Wait_Click,
            close_flag,
            self.ad_id_prefix + "video_countdown",
            exist_timeout=self.device.task_operation.get_video_ad_duration(28))
        second_video_flag = "领取奖励"

        def wait_and_finish() -> bool:
            return self.device.ui_operation_sequence(exist_waite_click)

        result = wait_and_finish()
        if result:
            if self.device.click_by_flag(second_video_flag):
                self.device.sleep_task_random(3)
                wait_and_finish()
        if self.device.exist_by_flag("领取额外金币"):  # 打开app
            self.device.click_by_name("close_view")
        self.device.click_by_flag(self.close_icon, timeout=3)
        self.device.click_by_flag(close_flag, timeout=1)
        self.device.click_by_flag(self.close_icon, timeout=1)
        return result

    def get_duration_reward(self) -> bool:
        if not self.go_task_page():
            return False
        ui_trigger = self.device.find_all_contain_text(ConstViewType.Button, "点可领", timeout=5)
        if True or ui_trigger and ui_trigger.click():
            sleep(3)
            if random.random() < 0.5:
                ad = self.device.find_all_contain_text(ConstViewType.Button, "去看广告得最高", timeout=5)
                if ad and ad.click():
                    self.reward_ad_video_item()
                    self.device.click_by_id("com.kuaishou.nebula.live_audience_plugin:id/live_close_place_holder")  # 直播
            else:
                self.device.click_by_image(self.close_icon, timeout=2)
            return True
        return False

    def every_time_clear(self):
        pass
