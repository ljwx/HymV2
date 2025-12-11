import random
from abc import ABC, abstractmethod
from time import sleep

from apppackage.AppPackage import AppPackageInfo
from device.DeviceManager import DeviceManager


class AppRunBase(ABC):
    first_check_in_probably = 0.3
    execute_ad_reward_probably = 0.5

    star_probable: float = 0.2
    comment_probable: float = 0.2
    works_probable: float = 0.2

    def __init__(self, app_info: AppPackageInfo, device: DeviceManager):
        self.app_info = app_info
        self.device = device

    def launch_app(self) -> bool:
        try:
            # if not self.device.is_app_running(self.packageInfo.package_name):
            self.device.start_app(self.app_info.package_name)
            sleep(4)
            self.common_step()
            return True
        except Exception as e:
            print("启动异常", e)
            return False

    def common_step(self) -> bool:
        first_check_in = random.random() < self.first_check_in_probably
        self.handle_lunch_dialog()
        if first_check_in and self.go_task_page():
            self.check_in()
        if self.go_main_home_page():
            self.main_task_loop()
        if not first_check_in and self.go_task_page():
            self.check_in()
        if random.random() < self.execute_ad_reward_probably and self.go_task_page():
            self.reward_ad_video_item()

    @abstractmethod
    def handle_lunch_dialog(self):
        ...

    @abstractmethod
    def go_main_home_page(self) -> bool:
        ...

    @abstractmethod
    def go_task_page(self) -> bool:
        ...

    @abstractmethod
    def get_balance(self) -> str | None:
        ...

    def check_in(self) -> bool:
        if not self.is_check_in():
            balance = self.get_balance()
            print(self.app_info.name, "余额", balance)
            result = self.execute_check_in()
            print(self.app_info.name, "签到结果", result)
            return result
        return False

    def is_check_in(self) -> bool:
        return False

    @abstractmethod
    def execute_check_in(self) -> bool:
        ...

    def main_task_loop(self):
        def task():
            self.main_task_item()
            star = random.random() < self.star_probable
            comment = random.random() < self.comment_probable
            works = random.random() < self.works_probable
            self.main_task_human(star, comment, works)

        self.device.task_operation.main_task_range(callback=lambda: task())

    @abstractmethod
    def main_task_item(self):
        ...

    @abstractmethod
    def main_task_human(self, star: bool, comment: bool, works: bool):
        ...

    @abstractmethod
    def reward_ad_video_item(self) -> bool:
        ...

    @abstractmethod
    def get_duration_reward(self):
        ...

    @abstractmethod
    def every_time_clear(self):
        ...
