from abc import abstractmethod

from app.appbase.data.ViewFlagsData import RewardVideoAdItemData, StartVideoTaskData
from app.appbase.lv.AppRunLv5DurationReward import AppRunLv5DurationReward
from apppackage.AppPackage import AppPackageInfo
from device.DeviceManager import DeviceManager


class AppRunLv6AdVideo(AppRunLv5DurationReward):
    def __init__(self, app_info: AppPackageInfo, device: DeviceManager):
        super().__init__(app_info, device)

    def start_video_task(self):
        flags = self.get_start_video_task_flags()

        def enter_success() -> bool:
            for enter_flag in flags.enter_flag:
                if self.device.click_by_flag(enter_flag, 4):
                    self.reward_ad_video_item()
                    return True
            return False

        def swipe_up_for_enter():
            self.device.swipe_up()
            self.device.sleep_operation_random()
            enter_success()

        self.logd("===进入视频广告===")
        if flags.is_go_home_page:
            if not self.go_main_home_page(select_tab=False):
                return

        if flags.is_go_task_pag and self.go_task_page():
            if enter_success():
                return
            else:
                swipe_up_for_enter()
        self.logd("===结束视频广告===", "enter")

    @abstractmethod
    def get_start_video_task_flags(self) -> StartVideoTaskData:
        ...

    def reward_ad_video_item(self) -> bool:
        flags = self.get_reward_ad_video_item_flags()
        result = False

        def final_close():
            for final_flag in flags.final_close_flag:
                self.device.click_by_flag(final_flag, 1)

        def execute_next_ad():
            if flags.next_ad_flag_sequence is None:
                return
            next_result = True
            for next_ad in flags.next_ad_flag_sequence:
                if not self.device.click_by_flag(next_ad, 3):
                    next_result = False
            if next_result:
                self.reward_ad_video_item()

        self.logd("===单个广告开始===")
        enter_result = False
        for start in flags.start_success_flag:
            if self.device.exist_by_flag(start, 5):
                enter_result = True
        if enter_result:
            self.logd("进入看广告")
            self.device.sleep_task_random(flags.wait_time_range)
            for continue_flag in flags.continue_flag:
                self.device.click_by_flag(continue_flag, 1)
            execute_next_ad()
            for close_flag in flags.close_flag:
                self.device.click_by_flag(close_flag, 1)
            final_close()
            result = True
        execute_next_ad()
        final_close()
        self.logd("===单个广告结束===", "enter")
        return result

    @abstractmethod
    def get_reward_ad_video_item_flags(self) -> RewardVideoAdItemData:
        ...
