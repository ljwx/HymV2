import traceback
from abc import abstractmethod

from app.appbase.data.ViewFlagsData import GetBalanceData
from app.appbase.lv.AppRunLv3CheckIn import AppRunLv3CheckIn
from apppackage.AppPackage import AppPackageInfo
from device.DeviceManager import DeviceManager


class AppRunLv4GetBalance(AppRunLv3CheckIn):
    def __init__(self, app_info: AppPackageInfo, device: DeviceManager):
        super().__init__(app_info, device)

    def execute_get_balance(self) -> str | None:
        flags = self.get_execute_get_balance_flags()

        def go_another_page() -> bool:
            if flags.enter_another_page is not None and flags.enter_another_page.need_enter_another_page:
                return self._enter_another_page(flags.enter_another_page)
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

        self.logd("===开始获取余额===")
        if flags.is_go_task_page:
            if not self.go_task_page():
                return None

        if go_another_page():
            balance = execute()
            self.device.press_back()
        else:
            balance = execute()
        self.logd("===获取余额结果===", balance, "enter")
        return balance

    @abstractmethod
    def get_execute_get_balance_flags(self) -> GetBalanceData:
        ...
