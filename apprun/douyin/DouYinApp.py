import asyncio
import random
from pathlib import Path
from time import sleep

from apprun.appbase.AppRunFather import AppRunFather
from apprun.appbase.data.ParamsData import IsGoTaskPageData
from apprun.appbase.data.ViewFlagsData import MainHomePageData, MainTaskPageData, MainTaskHumanData, \
    AppLaunchDialogData, \
    CheckInData, DurationRewardData, GetBalanceData, RewardVideoAdItemData, StartVideoTaskData
from apppackage.AppPackage import AppInfoDouYin
from constant.Const import ConstViewType, ConstFlag
from device.DeviceManager import DeviceManager
from device.uiview.FindUIInfo import FindUITargetInfo

parent_dir = Path(__file__).parent


class DouYinApp(AppRunFather):
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
        task_tab_icon = FindUITargetInfo(ConstViewType.Frame, size=(0.2033, 0.0730), position=(0.5, 0.9438),
                                         parent_name=ConstViewType.Frame, z_orders={'global': 0, 'local': 2},
                                         desc="福袋")
        task_page_success = FindUITargetInfo(ConstViewType.Texture, size=(0.2641, 0.071), position=(0.8475, 0.8962),
                                             parent_name=ConstViewType.Frame, z_orders={'global': 0, 'local': 1},
                                             desc="宝箱")
        return MainTaskPageData(first_go_main_page=True, task_page_enter_flag=task_tab_icon,
                                is_text_and_can_selected=False, task_page_ad_flag=[],
                                task_page_success_flag=task_page_success)

    def get_execute_check_in_flags(self) -> CheckInData:
        check_in_exit_flag = FindUITargetInfo(ConstViewType.Group, size=(0.675, 0.0097), position=(0.5, 0.4307),
                                              parent_name=ConstViewType.Group, z_orders={'global': 0, 'local': 3},
                                              desc="进度条")
        check_in_flag = FindUITargetInfo(ConstViewType.Group, size=(0.6183, 0.0550), position=(0.5, 0.6318),
                                         parent_name=ConstViewType.Group, z_orders={'global': 0, 'local': 1},
                                         desc="立即签到按钮,签到提醒也是这个")
        standby_check_id_flag = FindUITargetInfo(ConstViewType.Group, size=(0.1975, 0.0404), position=(0.8583, 0.3516),
                                                 parent_name=ConstViewType.Group, z_orders={'global': 0, 'local': 4},
                                                 desc="主动签到")
        success_flag = FindUITargetInfo(ConstViewType.Group, size=(0.6183, 0.0550), position=(0.5, 0.6318),
                                        parent_name=ConstViewType.Group, z_orders={'global': 0, 'local': 1},
                                        desc="打开签到提醒按钮")
        return CheckInData(is_go_task_page=True, first_force_ad_flag=None,
                           check_in_flag=[check_in_flag, standby_check_id_flag], success_flag=success_flag,
                           go_ad_video_flag=None, is_back_task=False, close_flag=ConstFlag.Back)

    def get_execute_get_balance_flags(self) -> GetBalanceData:
        balance_flag = FindUITargetInfo(ConstViewType.Group, size=(0.915, 0.1389), position=(0.5, 0.1794),
                                        parent_name=ConstViewType.Group,
                                        z_orders={'global': 0, 'local': 1}, )
        return GetBalanceData(is_go_task_page=True, enter_another_page=None, only_snapshot=True,
                              snapshot_path=self.balance_snapshot, balance_flag=balance_flag)

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

    def get_start_video_task_flags(self) -> StartVideoTaskData:
        enter_flag = FindUITargetInfo(ConstViewType.Group, contains_desc="分钟完成一次", desc="视频广告入口1")
        enter_standby = FindUITargetInfo(ConstViewType.Group, contains_desc="看广告视频，本次可得", desc="视频广告入口2")
        return StartVideoTaskData(is_go_home_page=True, is_go_task_page=True, enter_flag=[enter_flag, enter_standby])

    def get_reward_ad_video_item_flags(self) -> RewardVideoAdItemData:
        start_success_flag = FindUITargetInfo(ConstViewType.Group, contains_desc="秒后可领奖励", desc="读秒倒计时")
        start_success_flag2 = FindUITargetInfo(ConstViewType.Group, size=(0.1083, 0.0389), position=(0.4766, 0.0730),
                                               parent_name=ConstViewType.Group, z_orders={'global': 0, 'local': 1},
                                               desc="反馈按钮")
        close_ad_flag = ConstFlag.Desc + "领取成功，关闭，按钮"
        next_ad_flag = FindUITargetInfo(ConstViewType.Group, size=(0.7583, 0.3928), position=(0.5, 0.4632),
                                        offset_y=0.2, desc="再看一个的领取按钮")
        next_ad_close = FindUITargetInfo(ConstViewType.Image, size=(0.065, 0.0292), position=(0.8033, 0.3741),
                                         parent_name=ConstViewType.Group, z_orders={'global': 0, 'local': 3},
                                         desc="再看一个的关闭按钮")
        final_close = FindUITargetInfo(ConstViewType.Group, size=(0.7583, 0.3928), position=(0.5, 0.4632),
                                       offset_y=0.35, desc="再看一个的坚持退出按钮")
        return RewardVideoAdItemData(start_success_flag=[start_success_flag, start_success_flag2],
                                     wait_time_range=35,
                                     continue_flag=[self.id_prefix + "iv_back"],
                                     next_ad_flag_sequence=[close_ad_flag, next_ad_flag],
                                     close_flag=[close_ad_flag],
                                     final_close_flag=[close_ad_flag, final_close])

    def get_duration_reward(self) -> bool:
        super().get_duration_reward()
        target_info = FindUITargetInfo(ConstViewType.Group, contains_desc="看视频赚超多钱",
                                       desc="看视频赚超多钱")
        success_flag = FindUITargetInfo(ConstViewType.Group, size=(0.4891, 0.0288), position=(0.5, 0.4966),
                                        parent_name=ConstViewType.Group, z_orders={'global': 0, 'local': 5},
                                        desc="还可再赚的描述")
        close_icon = FindUITargetInfo(ConstViewType.Image, size=(0.075, 0.0333), position=(0.8041, 0.2985),
                                      parent_name=ConstViewType.Group, z_orders={'global': 0, 'local': 8},
                                      desc="直接关闭")

    def get_duration_reward_flags(self) -> DurationRewardData:
        reward_flag_dynamic = FindUITargetInfo(ConstViewType.Texture, size=(0.2641, 0.0711), position=(0.8475, 0.8962),
                                               z_orders={'global': 0, 'local': 1}, parent_name=ConstViewType.Frame,
                                               desc="宝箱图标")
        ad_flag = FindUITargetInfo(ConstViewType.Group, size=(0.5866, 0.0625), position=(0.5, 0.5535),
                                   z_orders={'global': 0, 'local': 3}, parent_name=ConstViewType.Group,
                                   desc="看广告按钮")
        close_flag = FindUITargetInfo(ConstViewType.Image, size=(0.075, 0.0333), position=(0.8041, 0.3164),
                                      parent_name=ConstViewType.Group, z_orders={'global': 0, 'local': 5})
        return DurationRewardData(is_go_task_page=True, reward_flag=reward_flag_dynamic,
                                  success_flag="开宝箱奖励已到账",
                                  go_ad_flag=ad_flag, close_flag=close_flag)

    def every_time_clear(self):
        pass
