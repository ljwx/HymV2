import asyncio
import random
from abc import ABC, abstractmethod
from time import sleep

from app.appbase.AppRunBase import AppRunBase
from app.appbase.data.ViewFlagsData import MainHomePageData, MainTaskPageData, MainTaskHumanData, AppLaunchDialogData
from apppackage.AppPackage import AppPackageInfo
from device.DeviceManager import DeviceManager
from device.operation.UIOperation import UIOperation, Operation

RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'  # 重置颜色


class AppRunCommon(AppRunBase):

    def __init__(self, app_info: AppPackageInfo, device: DeviceManager):
        super().__init__(app_info, device)

    async def get_main_task_item_duration(self, ad_flag: list[str], normal: list[str], long_flag: list[str]) -> tuple[
        bool, float]:
        default_duration = self.device.task_operation.get_main_task_duration()
        default_result = (False, default_duration)
        IS_AD = "AD"
        IS_NORMAL = "NORMAL"
        IS_MOVIE = "MOVIE"

        self.logd(f"{RED}开始判断{RESET}")

        async def judge_ad() -> tuple[str, float] | None:
            for ad in ad_flag:
                self.logd("开始判断ad")
                if await asyncio.to_thread(self.device.exist_by_flag, ad, 0.5):
                    duration = self.device.task_operation.get_video_ad_duration(1)
                    self.logd("当前主任务是广告", duration)
                    return IS_AD, duration
            self.logd("ad判断完了")
            return None

        async def judge_normal() -> tuple[str, float] | None:
            for nor in normal:
                self.logd("开始判断normal")
                if await asyncio.to_thread(self.device.exist_by_flag, nor, 0.5):
                    duration = self.device.task_operation.get_main_task_duration()
                    self.logd("当前主任务是常规item", duration)
                    return IS_NORMAL, duration
            self.logd("normal判断完了")
            return None

        async def judge_long() -> tuple[str, float] | None:
            for lon in long_flag:
                if await asyncio.to_thread(self.device.exist_by_flag, lon, 0.5):
                    duration = self.device.task_operation.get_main_task_duration_with_movie()
                    self.logd("当前主任务是长视频", duration)
                    return IS_MOVIE, duration
            return None

        result = await self.async_task([
            judge_ad(),
            judge_normal(),
            judge_long()
        ])

        if result:
            task_type, duration = result
            if task_type == IS_AD:
                self.logd(f"{RED}返回结果，广告：{RESET}", duration)
                return False, duration
            else:
                self.logd(f"{RED}返回结果，普通：{RESET}", duration)
                return True, duration

        return default_result

    def main_task_human(self, star: bool, comment: bool, works: bool):
        self.logd("===模拟常规操作===", star, comment, works)
        flag = self.get_main_human_flag()
        go_works_list = UIOperation(True, Operation.Click, flag.go_works_flag)
        works_list_success = UIOperation(True, Operation.Exist, flag.works_success_flag)
        if star and flag.star_flag:
            self.logd("点赞")
            self.device.click_by_flag(flag.star_flag)
            self.device.sleep_operation_random()
        if comment and flag.comment_flag:
            self.logd("看评论")
            self.device.click_by_flag(flag.comment_flag)
            self.device.sleep_operation_random(2)
            self.device.press_back()
            self.device.sleep_operation_random()
        if works and flag.go_works_flag:
            self.logd("去作品列表")
            if self.device.ui_operation_sequence(go_works_list, works_list_success):
                for i in range(random.randint(1, 5)):
                    item = self.device.find_list_by_child(flag.works_list_flag)
                    if item is not None and item.exists():
                        try:
                            self.device.sleep_operation_random()
                            item.click(focus=self.device.get_click_position_offset())
                            self.main_task_item()
                            self.device.press_back()
                            self.device.sleep_operation_random()
                        except Exception as e:
                            self.logd("点击作品项失败，可能不在屏幕内", str(e))
                    self.device.swipe_up()
                    sleep(self.device.get_click_wait_time())
                sleep(self.device.get_click_wait_time())
                self.device.press_back()
        self.logd("===常规操作结束===", "enter")

    @abstractmethod
    def get_main_human_flag(self) -> MainTaskHumanData:
        ...
