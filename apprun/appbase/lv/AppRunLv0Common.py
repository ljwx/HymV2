from abc import abstractmethod

from apprun.appbase.AppRunCommon import AppRunCommon
from apprun.appbase.data.ParamsData import CloseDialogData
from apprun.appbase.data.ViewFlagsData import GoAnotherPageData
from apppackage.AppPackage import AppPackageInfo
from device.DeviceManager import DeviceManager


class AppRunLvCommon(AppRunCommon):
    _skip_home_and_task_page = False

    def __init__(self, app_info: AppPackageInfo, device: DeviceManager):
        super().__init__(app_info, device)

    def _enter_another_page(self, data: GoAnotherPageData) -> bool:
        if self.device.click_by_flag(data.enter_another_page_flag):
            if self.device.exist_by_flag(data.another_page_success_flag, 8):
                return True
        return False

    def change_skip_home_task_page(self, skip: bool):
        self._skip_home_and_task_page = skip

    def close_task_page_dialog(self):
        flags = self.get_close_page_dialog_flags()
        skip = False
        if flags.task_page_skip_close_dialog_flags is not None:
            if self.device.exist_by_flags_or(flags.task_page_skip_close_dialog_flags):
                skip = True
        if not skip:
            self.device.click_by_flags_or(flags.task_page_dialog_flags)

    @abstractmethod
    def get_close_page_dialog_flags(self) -> CloseDialogData:
        ...
