import asyncio
import random
from pathlib import Path
from time import sleep

from poco.proxy import UIObjectProxy

from app.appbase.AppRunCommon import AppRunCommon
from app.appbase.data.ViewFlagsData import MainHomePageData, MainTaskPageData, MainTaskHumanData, AppLaunchDialogData
from apppackage.AppPackage import AppInfoKuaiShou, AppInfoDouYin
from constant.Const import ConstViewType, ConstFlag
from device.DeviceManager import DeviceManager
from device.operation.UIOperation import UIOperation, Operation
from device.uiview.FindUIInfo import FindUITargetInfo

parent_dir = Path(__file__).parent


class DouYinApp(AppRunCommon):
    app_info = AppInfoDouYin
    id_prefix = app_info.id_prefix
    ad_id_prefix = app_info.ad_id_prefix

    def __init__(self, device: DeviceManager):
        self.device = device
        super().__init__(self.app_info, device)
        self.resource_dir = "douyin/"
        self.balance_snapshot = str(parent_dir / "snapshot" / "balance" / (self.get_today_file_name() + ".jpg"))
        self.close_icon = self.resource_dir + "bg_white_close_icon.png"

    def handle_launch_dialog(self):
        super().handle_launch_dialog()
        pass

    def get_handle_launch_dialog_flag(self) -> AppLaunchDialogData:
        return AppLaunchDialogData(close_flags=[])

    def get_main_home_page_flag(self) -> MainHomePageData:
        return MainHomePageData(main_home_page_flag=self.id_prefix + "root_view", main_home_tab_flag="首页",
                                main_home_page_intercept_flag=None)

    def get_task_page_flag(self) -> MainTaskPageData:
        task_tab_icon = FindUITargetInfo(ConstViewType.Image, size=(0.1025, 0.0449), position=(0.4991, 0.9445),
                                         parent_name=ConstViewType.Frame, z_orders={'global': 0, 'local': 2},
                                         desc="福袋")
        task_page_success = FindUITargetInfo(ConstViewType.Texture, size=(0.2641, 0.071), position=(0.8475, 0.8962),
                                             parent_name=ConstViewType.Frame, z_orders={'global': 0, 'local': 1},
                                             desc="宝箱")
        return MainTaskPageData(first_go_main_page=True, task_page_enter_flag=task_tab_icon,
                                is_text_and_can_selected=False, task_page_ad_flag=[self.close_icon],
                                task_page_success_flag=task_page_success)

    def execute_check_in(self) -> bool:
        result = False
        check_in_flag = FindUITargetInfo(ConstViewType.Group, size=(0.675, 0.0097), position=(0.5, 0.4307),
                                         parent_name=ConstViewType.Group, z_orders={'global': 0, 'local': 3},
                                         desc="进度条")
        success_flag = FindUITargetInfo(ConstViewType.Group, size=(0.6183, 0.0550), position=(0.5, 0.6318),
                                        parent_name=ConstViewType.Group, z_orders={'global': 0, 'local': 1}, )
        if self.device.exist_by_flag(check_in_flag, 4):
            if self.device.click_by_flag(self.resource_dir + "check_in_success_close_icon.png", 2):
                self.device.sleep_operation_random()
                result = True

        standby_flag = FindUITargetInfo(ConstViewType.Group, size=(0.1975, 0.0404), position=(0.8583, 0.3516),
                                        parent_name=ConstViewType.Group, z_orders={'global': 0, 'local': 4},
                                        desc="主动签到")
        self.device.click_by_flag(standby_flag, 2)
        if self.device.exist_by_flag(success_flag, 4):
            result = True
        self.device.press_back()
        return result

    def execute_get_balance(self) -> str | None:
        balance_info = FindUITargetInfo(ConstViewType.Group, size=(0.915, 0.1389), position=(0.5, 0.1794),
                                        parent_name=ConstViewType.Group,
                                        z_orders={'global': 0, 'local': 1}, )
        balance_result = None
        balance_ui = self.device.exist_by_flag(balance_info)
        if balance_ui is not None:
            result = self.device.screenshot(save_path=self.balance_snapshot, ui=balance_ui)
            if result is not None:
                balance_result = self.balance_snapshot
        self.device.sleep_operation_random()
        return balance_result

    def main_task_item(self):
        exist_flag = self.id_prefix + "user_avatar"
        ads = [ConstFlag.Desc + "当前直播间可用", "广告", ConstFlag.Desc + "查看详情", ConstFlag.Desc + "立即下载"]
        nors = [ConstFlag.Desc + "音乐，@🧊创作的原声，按钮", "全屏观看", "拍同款"]
        lon = ["点击进入看全集", "听抖音", "合集"]
        if not self.device.exist_by_flag(exist_flag, 1.5):
            self.logd("非正常item，下一个")
            self.device.swipe_up()
            self.device.sleep_operation_random()
        normal, duration = asyncio.run(self.get_main_task_item_duration(ad_flag=ads, normal=nors, long_flag=lon))
        if normal and random.random() < 0.012:
            follow_button = FindUITargetInfo(ConstViewType.Image, size=(0.065, 0.0292), position=(0.9216, 0.4910),
                                             parent_name=ConstViewType.Button, z_orders={'global': 0, 'local': 18})
            self.device.click_by_flag(follow_button, 1)
        if self.device.exist_by_flag(exist_flag, 2):
            sleep(duration)
        else:
            self.device.swipe_up()
        return normal

    def get_main_human_flag(self) -> MainTaskHumanData:
        star = FindUITargetInfo(ConstViewType.Image, size=(0.0975, 0.043), position=(0.9141, 0.5438),
                                parent_name=ConstViewType.Frame, z_orders={'global': 0, 'local': 1})
        comment = FindUITargetInfo(ConstViewType.Image, size=(0.0975, 0.0438), position=(0.9141, 0.6277),
                                   parent_name=ConstViewType.Frame, z_orders={'global': 0, 'local': 1})
        return MainTaskHumanData(
            star_flag=star,
            comment_flag=comment,
            go_works_flag=self.id_prefix + "user_avatar",
            works_success_flag="获赞",
            works_list_flag=ConstViewType.Recycler)

    def start_video_task(self):

        def find_enter() -> bool | None:
            first = self.device.find_all_contain_name(ConstViewType.Group, "每20分钟完成一次广告任务", 2)
            if first is not None:
                first.click(focus=self.device.get_click_position_offset())
                return True
            second = self.device.find_all_contain_name(ConstViewType.Group, "看广告视频，", 2)
            if second is not None:
                second.click(focus=self.device.get_click_position_offset())
                return True
            return False

        def execute():
            self.reward_ad_video_item()
            sleep(self.device.get_click_wait_time())

        if self.go_task_page():
            if find_enter():
                execute()
            else:
                self.device.swipe_up()
                if find_enter():
                    execute()

    def reward_ad_video_item(self) -> bool:

        def ad_page_back():
            self.device.click_by_flag(self.id_prefix + "iv_back", 1)

        def first_video() -> bool:
            if self.device.find_all_contain_name(ConstViewType.Group, "秒后可领奖励", 4):
                self.device.sleep_operation_random(random.randint(33, 39))
                ad_page_back()
                if self.device.click_by_flag(ConstFlag.Desc + "领取成功，关闭，按钮", 4):
                    ad_page_back()
                    self.device.click_by_flag(
                        FindUITargetInfo(ConstViewType.Image, size=(0.065, 0.0292), position=(0.8033, 0.3741),
                                         parent_name=ConstViewType.Group, z_orders={'global': 0, 'local': 3}), 1)
                ad_page_back()
            return False

        def second_video() -> bool:
            if self.device.click_by_flag(self.resource_dir + "video_ad_second_flag.png", 4):
                self.device.sleep_task_random(3)
                first_video()

        for i in range(2):
            first_video()
            second_video()
            ad_page_back()
        close_ad_icon = FindUITargetInfo(ConstViewType.Image, size=(0.065, 0.0292), position=(0.8033, 0.3741),
                                         parent_name=ConstViewType.Group, z_orders={'global': 0, 'local': 3})
        self.device.click_by_flag(close_ad_icon, 1)
        self.device.click_by_flag(close_ad_icon, 1)
        return True

    def get_duration_reward(self) -> bool:
        if not self.go_task_page():
            return False
        close_icon = FindUITargetInfo(ConstViewType.Image, size=(0.075, 0.0333), position=(0.8041, 0.3164),
                                      parent_name=ConstViewType.Group, z_orders={'global': 0, 'local': 5})
        go_ad_enter = FindUITargetInfo(ConstViewType.Group, size=(0.5866, 0.0625), position=(0.5, 0.5535),
                                       z_orders={'global': 0, 'local': 3}, parent_name=ConstViewType.Group)

        def reward_ad_video() -> bool:
            if self.device.click_by_flag(go_ad_enter, 4):
                self.reward_ad_video_item()
                return True
            return False

        if self.device.click_by_flag(ConstFlag.Desc + "开宝箱得金币", 2):  # 方式一
            reward_ad_video()
            return True

        reward_icon = FindUITargetInfo(ConstViewType.Texture, size=(0.2641, 0.0711), position=(0.8475, 0.8962),
                                       z_orders={'global': 0, 'local': 3}, parent_name=ConstViewType.Group)
        if self.device.click_by_flag(reward_icon, 1):  # 方式二
            reward_ad_video()
            return True
        self.device.click_by_flag(close_icon, 1)
        return False

    def every_time_clear(self):
        pass
