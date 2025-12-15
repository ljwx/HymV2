import asyncio
import random
import threading
import time
import traceback
from abc import ABC, abstractmethod
from datetime import datetime
from time import sleep
from typing import Any

from apppackage.AppPackage import AppPackageInfo
from device.DeviceManager import DeviceManager
from logevent.Log import Log
from utils.json_cache import JsonCacheUtils

COLOR_RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
COLOR_RESET = '\033[0m'  # 重置颜色
print_lock = threading.Lock()


class AppRunBase(ABC):
    test_main_task_times = None

    def __init__(self, app_info: AppPackageInfo, device: DeviceManager):
        def _get_value(key: str) -> float:
            entry = JsonCacheUtils.get_flag(key, default=None, cache_path="run_config")
            if isinstance(entry, dict):
                return entry.get("value", 0.5)
            return 0.5

        # 读取概率配置，如缺失则使用 0.0 兜底，避免 None.get 报错
        self.first_check_in_probably = _get_value("first_check_in_probably")
        self.execute_ad_reward_probably = _get_value("execute_ad_reward_probably")
        self.star_probable = _get_value("star_probable")
        self.comment_probable = _get_value("comment_probable")
        self.works_probable = _get_value("works_probable")
        self.app_info = app_info
        self.device = device

    def launch_app(self) -> bool:
        try:
            self.logd("启动")
            # if not self.device.is_app_running(self.packageInfo.package_name):
            self.device.start_app(self.app_info.package_name)
            sleep(6)
            self.common_step()
            return True
        except Exception as e:
            self.logd("启动异常", e)
            traceback.print_exc()
            return False

    def common_step(self) -> bool:
        first_check_in = random.random() < self.first_check_in_probably
        self.logd("是否先签到", first_check_in)
        self.logd("处理启动后弹窗")
        self.handle_launch_dialog()

        def check_in() -> bool:
            if not self.is_check_in() and self.go_task_page():
                self.check_in()

        if first_check_in:
            check_in()
        if self.go_main_home_page(select_tab=True):
            self.main_task_loop()
        if not first_check_in:
            check_in()
        self.logd("===获取时间段奖励===")
        self.get_duration_reward()
        self.logd("===时间段奖励结束===", "enter")
        if random.random() < self.execute_ad_reward_probably and self.go_task_page():
            times = random.randint(1, 3)
            self.logd("执行视频广告任务", str(times), "次")
            for i in range(times):
                self.logd("===开始视频广告item===")
                self.start_video_task()
                self.logd("===结束视频广告item===", "enter")

    @abstractmethod
    def handle_launch_dialog(self):
        ...

    @abstractmethod
    def go_main_home_page(self, select_tab: bool = False) -> bool:
        ...

    @abstractmethod
    def go_task_page(self) -> bool:
        ...

    @abstractmethod
    def get_balance(self) -> str | None:
        ...

    def check_in(self) -> bool:
        self.logd("===准备签到===")
        if not self.is_check_in():
            self.logd("现在执行签到")
            result = self.execute_check_in()
            if result:
                JsonCacheUtils.set_flag_today(self.app_info.name, True)
            self.logd("签到结果", result)
            if self.app_info.enable_balance:
                self.logd("去获取余额")
                balance = self.get_balance()
                if balance:
                    JsonCacheUtils.set_flag_today(self.app_info.name + ",b", balance, cache_path="balance")
                self.logd("余额", balance)
            self.logd("===签到执行完毕===", "enter")
            return result
        return False

    def is_check_in(self) -> bool:
        return JsonCacheUtils.get_flag_today(self.app_info.name, False)

    @abstractmethod
    def execute_check_in(self) -> bool:
        ...

    def main_task_loop(self):
        self.logd("开始主线任务")

        def task():
            self.logd("====开始单个任务====")
            if JsonCacheUtils.get_flag("skip_main_task", False, cache_path="run_config").get("value"):
                return
            self.every_time_clear()
            self.device.swipe_up()
            is_normal = self.main_task_item()
            star = (random.random() < self.star_probable) if is_normal else False
            comment = (random.random() < self.comment_probable) if is_normal else False
            works = (random.random() < self.works_probable) if is_normal else False
            self.device.sleep_operation_random()
            self.main_task_human(star, comment, works)
            self.go_main_home_page()
            self.logd("====结束单个任务====", "enter")
            if random.random() < 0.07:
                self.device.press_home()
                sleep(random.randint(4, 32))
                self.device.start_app(self.app_info.package_name)
                self.device.sleep_operation_random()

        self.device.task_operation.main_task_range(callback=lambda: task(), test_times=self.test_main_task_times)

    @abstractmethod
    def main_task_item(self) -> bool:
        ...

    @abstractmethod
    def get_main_task_item_duration(self, ad_flag: list[str], normal: list[str], long_flag: list[str]) -> tuple[
        bool, float]:
        ...

    @abstractmethod
    def main_task_human(self, star: bool, comment: bool, works: bool):
        ...

    @abstractmethod
    def start_video_task(self):
        ...

    @abstractmethod
    def reward_ad_video_item(self) -> bool:
        ...

    @abstractmethod
    def get_duration_reward(self) -> bool:
        ...

    @abstractmethod
    def every_time_clear(self):
        ...

    async def async_task(self, task_def: list) -> Any | None:
        tasks = []
        for item_def in task_def:
            tasks.append(asyncio.create_task(item_def))
        while tasks:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                result = task.result()
                if result:
                    for p in pending:
                        p.cancel()
                    return result
            tasks = list(pending)
        return None

    def logd(self, *content):
        now = datetime.now()
        formatted_time = now.strftime("%Y-%m-%d %H:%M:%S")
        with print_lock:
            print(Log.filter, formatted_time, self.app_info.name, *content, flush=True)
        for item in content:
            if str(item).lower().endswith("enter"):
                print("", flush=True)
