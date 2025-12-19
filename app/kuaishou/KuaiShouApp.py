import asyncio
import random
from time import sleep

from app.appbase.AppRunFather import AppRunFather
from app.appbase.data.ViewFlagsData import MainHomePageData, MainTaskPageData, MainTaskHumanData, AppLaunchDialogData, \
    RewardVideoAdItemData, StartVideoTaskData, DurationRewardData, CheckInData, GetBalanceData, GoAnotherPageData
from apppackage.AppPackage import AppInfoKuaiShou
from constant.Const import ConstViewType, ConstFlag
from device.DeviceManager import DeviceManager
from device.operation.UIOperation import UIOperation, Operation
from device.uiview.FindUIInfo import FindUITargetInfo


class KuaiShouApp(AppRunFather):
    app_info = AppInfoKuaiShou
    id_prefix = app_info.id_prefix
    ad_id_prefix = app_info.ad_id_prefix

    def __init__(self, device: DeviceManager):
        self.device = device
        super().__init__(self.app_info, device)
        self.resource_dir = "kuaishou/"
        self.close_icon = self.resource_dir + "task_tab_page_close_icon.png"
        self.check_in_icon = self.resource_dir + "check_in_icon.png"
        self.task_page_close_icon = FindUITargetInfo(ConstViewType.Image, (0.0708, 0.0314), (0.92, 0.1921),
                                                     parent_name=ConstViewType.View)

    def handle_launch_dialog(self):
        super().handle_launch_dialog()
        if self.device.exist_by_flag("邀请2个新用户必得"):
            close_icon = self.device.exist_by_flag(
                FindUITargetInfo(ConstViewType.Image, (0.0758, 0.0340), (0.5, 0.7003)))
            if close_icon is not None:
                close_icon.click(focus=self.device.get_click_position_offset())
        # if self.device.exist_by_flag("朋友推荐", 1):
        #     self.device.click_by_flag("com.kuaishou.nebula:id/close_btn", 2)
        # self.device.ui_operation_sequence(UIOperation(False, Operation.Exist_Click, "","限时大红包", "邀请新用户"))
        pass

    def get_handle_launch_dialog_flag(self) -> AppLaunchDialogData:
        return AppLaunchDialogData(close_flags=[self.id_prefix + "close_btn"])

    def get_main_home_page_flag(self) -> MainHomePageData:
        return MainHomePageData(main_home_page_flag=self.id_prefix + "bottom_bar_container", main_home_tab_flag="首页",
                                main_home_page_intercept_flag=None)

    def get_task_page_flag(self) -> MainTaskPageData:
        ["瓜分百亿金币", ""]
        return MainTaskPageData(first_go_main_page=True, task_page_enter_flag="去赚钱", is_text_and_can_selected=True,
                                task_page_ad_flag=[self.task_page_close_icon, self.close_icon],
                                task_page_success_flag="任务中心")

    def get_execute_check_in_flags(self) -> CheckInData:
        return CheckInData(is_go_task_page=True, first_force_ad_flag=None,
                           check_in_flag=[self.check_in_icon, "立即签到"],
                           success_flag="明日签到可领", go_ad_video_flag="去看视频", is_back_task=False,
                           close_flag=self.task_page_close_icon)

    def get_execute_get_balance_flags(self) -> GetBalanceData:
        another_page = GoAnotherPageData(need_enter_another_page=True,
                                         enter_another_page_flag="我的金币",
                                         another_page_success_flag="我的收益")
        balance_flag = FindUITargetInfo(ConstViewType.Text, size=(0.23, 0.0486), position=(0.1908, 0.1898))
        return GetBalanceData(is_go_task_page=True, enter_another_page=another_page,
                              only_snapshot=False, snapshot_path=None, balance_flag=balance_flag)

    def main_task_item(self):
        shopping_ad_video = self.id_prefix + "ad_download_progress"
        ask_ad_video = "咨询"
        ad_follow_flag = self.id_prefix + "slide_play_right_link_icon"
        live_video_text = "点击进入直播间"
        ads = [shopping_ad_video, ask_ad_video, ad_follow_flag]
        nors = ["全屏观看", "作者声明：演绎情节，仅供娱乐",
                self.id_prefix + "general_entry_single_root_view",
                self.id_prefix + "pic_text", self.id_prefix + "create_date_tv"]
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
            star_flag=self.id_prefix + "like_icon",
            comment_flag=self.id_prefix + "comment_icon",
            go_works_flag=self.id_prefix + "user_name_text_view",
            works_success_flag=self.id_prefix + "profile_user_kwai_id",
            works_list_flag=self.id_prefix + "recycler_view")

    def get_start_video_task_flags(self) -> StartVideoTaskData:
        return StartVideoTaskData(is_go_home_page=True, is_go_task_pag=True, enter_flag=["看广告得金币"])

    def get_reward_ad_video_item_flags(self) -> RewardVideoAdItemData:
        close_ad_flag = self.ad_id_prefix + "video_countdown_end_icon"
        close_view = ConstFlag.Desc + "close_view"  # 打开app
        live_flag = "com.kuaishou.nebula.live_audience_plugin:id/live_audience_bottom_mask_view"
        close_live = "com.kuaishou.nebula.live_audience_plugin:id/live_close_place_holder"
        return RewardVideoAdItemData(start_success_flag=[self.ad_id_prefix + "video_countdown", live_flag],
                                     wait_time_range=35,
                                     continue_flag=[close_ad_flag], next_ad_flag_sequence=["领取奖励"],
                                     close_flag=[close_ad_flag, close_view],
                                     final_close_flag=[close_ad_flag, close_view, close_live, close_view])

    def get_duration_reward_flags(self) -> DurationRewardData:
        reward_flag = FindUITargetInfo(ConstViewType.View, size=(0.2, 0.0827), position=(0.8691, 0.8651),
                                       parent_name=ConstViewType.View, z_orders={'global': 0, 'local': 0})
        ad_flag = FindUITargetInfo(ConstViewType.Button, size=(0.5058, 0.0666), position=(0.5016, 0.6322),
                                   parent_name=ConstViewType.View, z_orders={'global': 0, 'local': 0})
        close_flag = FindUITargetInfo(ConstViewType.Image, size=(0.0708, 0.0318), position=(0.92, 0.1749),
                                      parent_name=ConstViewType.View, z_orders={'global': 0, 'local': 0})
        return DurationRewardData(is_go_task_page=True, reward_flag=reward_flag, success_flag="开宝箱奖励已到账",
                                  go_ad_flag=ad_flag, close_flag=close_flag)

    def get_duration_reward(self) -> bool:
        super().get_duration_reward()
        reward_lite = FindUITargetInfo(ConstViewType.Text, contains_text="金币立即领取", desc="领金币按钮")
        close_icon = FindUITargetInfo(ConstViewType.Text, size=(0.07833, 0.0367), position=(0.9275, 0.2250),
                                      parent_name=ConstViewType.View, z_orders={'global': 0, 'local': 0})
        if self.device.click_by_flag(reward_lite):
            if self.device.exist_by_flag("任务完成奖励"):
                self.device.click_by_flag(close_icon, timeout=2)
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
