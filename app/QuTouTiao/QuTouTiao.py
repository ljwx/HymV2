import asyncio
import random
from time import sleep

from poco.proxy import UIObjectProxy

from app.appbase.AppRunCommon import AppRunCommon
from app.appbase.data.ViewFlagsData import MainHomePageData, MainTaskPageData, MainTaskHumanData, AppLaunchDialogData
from apppackage.AppPackage import AppInfoKuaiShou
from constant.Const import ConstViewType, ConstFlag
from device.DeviceManager import DeviceManager
from device.operation.UIOperation import UIOperation, Operation
from device.uiview.FindUIInfo import FindUITargetInfo


class QuTouTiao(AppRunCommon):
    app_info = AppInfoKuaiShou
    id_prefix = app_info.id_prefix
    ad_id_prefix = app_info.ad_id_prefix

    def __init__(self, device: DeviceManager):
        self.device = device
        super().__init__(self.app_info, device)
        self.resource_dir = "kuaishou/"
        self.close_icon = self.resource_dir + "task_tab_page_close_icon.png"
        self.check_in_icon = self.resource_dir + "check_in_icon.png"

    def handle_launch_dialog(self):
        super().handle_launch_dialog()
        # if self.device.exist_by_flag("朋友推荐", 1):
        #     self.device.click_by_flag("com.kuaishou.nebula:id/close_btn", 2)
        # self.device.ui_operation_sequence(UIOperation(False, Operation.Exist_Click, "","限时大红包", "邀请新用户"))
        pass

    def get_handle_launch_dialog_flag(self) -> AppLaunchDialogData:
        return AppLaunchDialogData([])

    def get_main_home_page_flag(self) -> MainHomePageData:
        home_tab = FindUITargetInfo(ConstViewType.Frame, size=(0.2, 0.0546), position=(0.1, 0.953),
                                    parent_name=ConstViewType.Linear, z_orders={'global': 0, 'local': 1})
        close = FindUITargetInfo(ConstViewType.Image, size=(0.0975, 0.0438), position=(0.4991, 0.7419),
                                 parent_name=ConstViewType.Relative, z_orders={'global': 0, 'local': 3})
        return MainHomePageData(home_tab, home_tab, [close])

    def get_task_page_flag(self) -> MainTaskPageData:
        ad_close = FindUITargetInfo(ConstViewType.Image, size=(.04333, 0.0194), position=(0.8391, 0.2610),
                                    parent_name=ConstViewType.Relative, z_orders={'global': 0, 'local': 2})
        return MainTaskPageData(True, "任务", "换一批", [ad_close])

    def execute_check_in(self) -> bool:
        def loop_video_ad():
            for i in range(3):
                self.reward_ad_video_item()

        loop_video_ad()
        result = False
        close_icon = FindUITargetInfo(ConstViewType.Image, (0.0816, 0.0367), (0.8508, 0.1239),
                                      parent_name=ConstViewType.Linear, z_orders={'global': 0, 'local': 1})
        if self.device.click_by_flag("直接签到，不提现", 4):
            if self.device.exist_by_flag("已领", 4):
                result = True
                self.device.sleep_operation_random()
                self.device.click_by_flag(close_icon, 2)
        if self.device.click_by_flag("立即签到", 2):
            loop_video_ad()
        return result

    def execute_get_balance(self) -> str | None:
        balance_info = FindUITargetInfo(ConstViewType.Text, size=(0.1491, 0.0183), position=(0.2616, 0.0876),
                                        parent_name=ConstViewType.Group, z_orders={'global': 0, 'local': 2})
        balance = None
        balance_ui = self.device.exist_by_flag(balance_info)
        if balance_ui is not None:
            balance = balance_ui.get_text()
        return balance

    def main_task_item(self):
        recycler = """
        type :  android.view.ViewGroup 
	  name :  com.jifen.qukan:id/bjc 
	  enabled :  True 
	  visible :  True 
	  resourceId :  b'com.jifen.qukan:id/bjc' 
	  zOrders :  {'global': 0, 'local': 2} 
	  package :  b'com.jifen.qukan' 
	  anchorPoint :  [0.5, 0.5] 
	  dismissable :  False 
	  checkable :  False 
	  scale :  [1, 1] 
	  boundsInParent :  [1, 0.7808988764044944] 
	  focusable :  True 
	  touchable :  True 
	  longClickable :  False 
	  size :  [1.0, 0.7808988764044944] 
	  pos :  [0.5, 0.5352059925093633] 
	  focused :  False 
	  checked :  False 
	  editalbe :  False 
	  selected :  False 
	  scrollable :  False 
        """

    item = """
    type :  android.widget.RelativeLayout 
	  name :  android.widget.RelativeLayout 
	  enabled :  True 
	  visible :  True 
	  zOrders :  {'global': 0, 'local': 4} 
	  package :  b'com.jifen.qukan' 
	  anchorPoint :  [0.5, 0.5] 
	  dismissable :  False 
	  checkable :  False 
	  scale :  [1, 1] 
	  boundsInParent :  [1, 0.21797752808988763] 
	  focusable :  True 
	  touchable :  True 
	  longClickable :  False 
	  size :  [1.0, 0.2104868913857678] 
	  pos :  [0.5, 0.8205992509363296] 
	  focused :  False 
	  checked :  False 
	  editalbe :  False 
	  selected :  False 
	  scrollable :  False 
	  5个子view是视频，
	  4个是文章
    """

    detail = "我来说两句..."

    reward = """
    type :  android.view.View 
	  name :  com.jifen.qukan:id/ex 
	  enabled :  True 
	  visible :  True 
	  resourceId :  b'com.jifen.qukan:id/ex' 
	  zOrders :  {'global': 0, 'local': 1} 
	  package :  b'com.jifen.qukan' 
	  anchorPoint :  [0.5, 0.5] 
	  dismissable :  False 
	  checkable :  False 
	  scale :  [1, 1] 
	  boundsInParent :  [0.1625, 0.07303370786516854] 
	  focusable :  False 
	  touchable :  False 
	  longClickable :  False 
	  size :  [0.1625, 0.07303370786516854] 
	  pos :  [0.8875, 0.8217228464419476] 
	  focused :  False 
	  checked :  False 
	  editalbe :  False 
	  selected :  False 
	  scrollable :  False 
    """

    reward_close = """
        exist = "+”  多少金币
        close = 
        type :  android.widget.ImageView 
	  name :  com.jifen.qukan:id/asi 
	  enabled :  True 
	  visible :  True 
	  resourceId :  b'com.jifen.qukan:id/asi' 
	  zOrders :  {'global': 0, 'local': 3} 
	  package :  b'com.jifen.qukan' 
	  anchorPoint :  [0.5, 0.5] 
	  dismissable :  False 
	  checkable :  False 
	  scale :  [1, 1] 
	  boundsInParent :  [0.06, 0.02696629213483146] 
	  focusable :  True 
	  touchable :  True 
	  longClickable :  False 
	  size :  [0.06, 0.02696629213483146] 
	  pos :  [0.8383333333333334, 0.27228464419475656] 
	  focused :  False 
	  checked :  False 
	  editalbe :  False 
	  selected :  False 
	  scrollable :  False 
    """

        shopping_ad_video = self.id_prefix + "ad_download_progress"
        ask_ad_video = "咨询"
        ad_follow_flag = self.id_prefix + "slide_play_right_link_icon"
        live_video_text = "点击进入直播间"
        ads = [shopping_ad_video, ask_ad_video, ad_follow_flag]
        nors = [self.id_prefix + "create_date_tv", "全屏观看", "作者声明：演绎情节，仅供娱乐",
                self.id_prefix + "general_entry_single_root_view",
                self.id_prefix + "pic_text"]
        lon = ["继续观看完整版", "完整版", "合集"]
        if not self.device.exist_by_flag(self.id_prefix + "follow_avatar_view", 1.5):
            self.logd("非正常item，下一个")
            self.device.swipe_up()
            self.device.sleep_operation_random()
        normal, duration = asyncio.run(self.get_main_task_item_duration(ad_flag=ads, normal=nors, long_flag=lon))
        if normal and random.random() < 0.011:
            self.device.click_by_flag(self.id_prefix + "follow_button", 1)
        if self.device.exist_by_flag(self.id_prefix + "follow_avatar_view", 2):
            wait = UIOperation(True, Operation.Wait, "", exist_waite_time=duration)
            self.device.ui_operation_sequence(wait)
        else:
            self.device.swipe_up()
        return normal


def get_main_human_flag(self) -> MainTaskHumanData:
    return MainTaskHumanData(
        self.id_prefix + "like_icon", self.id_prefix + "comment_icon",
        self.id_prefix + "user_name_text_view", self.id_prefix + "profile_user_kwai_id",
        self.id_prefix + "recycler_view")


def start_video_task(self):
    video_ad_enter = "看广告领奖励"

    def execute():
        self.reward_ad_video_item()
        self.device.sleep_operation_random()

    def exist() -> UIObjectProxy | None:
        ui = self.device.exist_by_flag(video_ad_enter)
        if ui is not None:
            x, y = ui.get_position()
            self.device.click_by_flag(ConstFlag.Position + "("")", 1)

    if self.go_task_page():
        if self.device.click_by_flag(video_ad_enter, 4):
            execute()
        else:
            self.device.swipe_up()
            if self.device.click_by_flag(video_ad_enter, 4):
                execute()


def reward_ad_video_item(self) -> bool:
    close_flag = FindUITargetInfo(ConstViewType.Image, size=(0.0433, 0.0194), position=(0.9108, 0.0696),
                                  parent_name=ConstViewType.Frame, z_orders={'global': 0, 'local': 1})

    def first_video() -> bool:
        if self.device.exist_by_flag("奖励将于", 6) or self.device.exist_by_flag("打开", 1):
            self.device.sleep_task_random(33)
            if self.device.exist_by_flag("立即打开", 2):
                self.device.click_by_flag(close_flag, 1)
            self.device.click_by_flag(close_flag)
            return True
        return False

    def web_scan():
        pass

    first_video()
    if self.device.click_by_flag("放弃福利", 2):
        self.device.sleep_task_random(19)
    self.device.click_by_flag(close_flag)
    return True


def get_duration_reward(self) -> bool:
    if not self.go_task_page():
        return False
    trigger1 = self.device.find_all_contain_text(ConstViewType.Text, "金币立即领取", timeout=3)
    if trigger1 is not None:
        trigger1.click(focus=self.device.get_click_position_offset())
        if self.device.exist_by_flag("任务完成奖励"):
            self.device.click_by_flag(self.close_icon, timeout=2)
    ui_trigger = self.device.find_all_contain_text(ConstViewType.Button, "点可领", timeout=2)
    if ui_trigger is not None:
        ui_trigger.click(focus=self.device.get_click_position_offset())
        sleep(3)
        if random.random() < 0.5:
            ad = self.device.find_all_contain_text(ConstViewType.Button, "去看广告得最高", timeout=5)
            if ad is not None:
                ad.click(focus=self.device.get_click_position_offset())
                self.reward_ad_video_item()
                self.device.click_by_flag("com.kuaishou.nebula.live_audience_plugin:id/live_close_place_holder",
                                        4)  # 直播
        else:
            self.device.click_by_flag(self.close_icon, timeout=2)
        return True
    return False


def other_reward_task1(self) -> bool:
    go = self.device.click_by_flag("到饭点领饭补", timeout=3)
    if go:
        if self.device.click_by_flag("看广告", 4):
            self.reward_ad_video_item()

        if self.device.click_by_flag("看广告领饭补", 3):
            self.reward_ad_video_item()
            self.device.press_back()


def every_time_clear(self):
    pass
