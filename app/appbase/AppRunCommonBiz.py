import traceback
from abc import abstractmethod

from app.appbase.AppRunCommon import AppRunCommon
from app.appbase.data.ViewFlagsData import RewardVideoAdItemData, StartVideoTaskData, DurationRewardData, CheckInData, \
    GoAnotherPageData, GetBalanceData
from apppackage.AppPackage import AppPackageInfo
from device.DeviceManager import DeviceManager


class AppRunCommonBiz(AppRunCommon):
    def __init__(self, app_info: AppPackageInfo, device: DeviceManager):
        super().__init__(app_info, device)

    def __enter_another_page(self, data: GoAnotherPageData) -> bool:
        if self.device.click_by_flag(data.enter_another_page_flag):
            if self.device.exist_by_flag(data.another_page_success_flag, 8):
                return True
        return False

    def execute_check_in(self) -> bool:
        flags = self.get_execute_check_in_flags()
        check_in_result = False

        def force_ad_video():
            if flags.first_force_ad_flag is not None:
                for force_ad in flags.first_force_ad_flag:
                    if self.device.click_by_flag(force_ad, 1):
                        self.reward_ad_video_item()

        def execute() -> bool:
            force_ad_video()
            perform_result = False
            execute_result = False
            for check_in in flags.check_in_flag:
                if self.device.click_by_flag(check_in, 3):
                    perform_result = True
            if perform_result and self.device.exist_by_flag(flags.success_flag, 5):
                execute_result = True
            self.logd("签到结果", execute_result)
            return execute_result

        self.logd("===开始执行签到===")
        if flags.is_go_task_page:
            if self.go_task_page():
                check_in_result = execute()
        else:
            check_in_result = execute()
        if check_in_result and flags.go_ad_video_flag is not None:
            self.device.sleep_operation_random()
            if self.device.click_by_flag(flags.go_ad_video_flag, 1):
                self.reward_ad_video_item()
        if flags.is_back_task:
            self.go_task_page()
        if check_in_result and flags.close_flag is not None:
            self.device.click_by_flag(flags.close_flag, 2)
        self.logd("===签到结束===", "enter")
        return check_in_result

    @abstractmethod
    def get_execute_check_in_flags(self) -> CheckInData:
        ...

    def execute_get_balance(self) -> str | None:
        flags = self.get_execute_get_balance_flags()

        def go_another_page() -> bool:
            if flags.enter_another_page is not None and flags.enter_another_page.need_enter_another_page:
                return self.__enter_another_page(flags.enter_another_page)
            return False

        def execute() -> str | None:
            ui = self.device.exist_by_flag(flags.balance_flag)
            if ui is None:
                return None
            if flags.only_snapshot:
                self.device.screenshot(flags.snapshot_path, ui=ui)
                return flags.snapshot_path
            else:
                try:
                    return ui.get_text()
                except Exception as e:
                    self.logd("获取text异常", e)
                    traceback.print_exc()
            return None

        if flags.is_go_task_page:
            if not self.go_task_page():
                return None

        if go_another_page():
            balance = execute()
            self.device.press_back()
        else:
            balance = execute()
        return balance

    @abstractmethod
    def get_execute_get_balance_flags(self) -> GetBalanceData:
        ...

    def start_video_task(self):
        flags = self.get_start_video_task_flags()

        def enter_success() -> bool:
            if self.device.click_by_flag(flags.enter_flag, 4):
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

    def get_duration_reward(self) -> bool:
        flags = self.get_duration_reward_flags()

        def execute() -> bool:
            result = False
            if self.device.click_by_flag(flags.reward_flag, 3):
                self.device.sleep_operation_random()
                if self.device.exist_by_flag(flags.success_flag, 8):
                    result = True
                    if flags.go_ad_flag is not None:
                        if self.device.click_by_flag(flags.go_ad_flag, 1):
                            self.device.sleep_operation_random()
                            self.reward_ad_video_item()
            self.device.click_by_flag(flags.close_flag, 2)
            return result

        self.logd("====获取时段奖励====")
        if flags.is_go_task_page:
            if self.go_task_page():
                execute()
        else:
            execute()
        self.logd("====时间段奖励结束====", "enter")

    @abstractmethod
    def get_duration_reward_flags(self) -> DurationRewardData:
        ...
