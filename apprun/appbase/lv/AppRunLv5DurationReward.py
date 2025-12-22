from abc import abstractmethod

from apprun.appbase.data.ViewFlagsData import DurationRewardData
from apprun.appbase.lv.AppRunLv4GetBalance import AppRunLv4GetBalance
from apppackage.AppPackage import AppPackageInfo
from device.DeviceManager import DeviceManager


class AppRunLv5DurationReward(AppRunLv4GetBalance):
    def __init__(self, app_info: AppPackageInfo, device: DeviceManager):
        super().__init__(app_info, device)

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