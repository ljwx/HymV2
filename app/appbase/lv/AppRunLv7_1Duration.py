import asyncio

from app.appbase.lv.AppRunLv6AdVideo import AppRunLv6AdVideo
from apppackage.AppPackage import AppPackageInfo
from device.DeviceManager import DeviceManager


class AppRunLv7_1Duration(AppRunLv6AdVideo):
    def __init__(self, app_info: AppPackageInfo, device: DeviceManager):
        super().__init__(app_info, device)

    async def get_main_task_item_duration(self, ad_flag: list[str], normal: list[str], long_flag: list[str]) -> tuple[
        bool, float]:
        default_duration = self.device.task_operation.get_main_task_duration()
        default_result = (False, default_duration)
        IS_AD = "AD"
        IS_NORMAL = "NORMAL"
        IS_MOVIE = "MOVIE"

        self.logd(f"{self.COLOR_RED}开始判断{self.COLOR_RESET}")

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
                self.logd(f"{self.COLOR_RED}返回结果，广告：{self.COLOR_RESET}", duration)
                return False, duration
            else:
                self.logd(f"{self.COLOR_RED}返回结果，普通：{self.COLOR_RESET}", duration)
                return True, duration

        return default_result
