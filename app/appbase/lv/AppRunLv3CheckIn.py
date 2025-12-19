from abc import abstractmethod

from app.appbase.data.ViewFlagsData import CheckInData
from app.appbase.lv.AppRunLv2GoTask import AppRunLv2GoTask
from apppackage.AppPackage import AppPackageInfo
from device.DeviceManager import DeviceManager


class AppRunLv3CheckIn(AppRunLv2GoTask):
    def __init__(self, app_info: AppPackageInfo, device: DeviceManager):
        super().__init__(app_info, device)

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
