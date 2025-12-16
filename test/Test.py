from abc import ABC, abstractmethod

from airtest.core.api import snapshot
from poco.proxy import UIObjectProxy

from app.douyin.DouYinApp import DouYinApp
from app.kuaishou.KuaiShouApp import KuaiShouApp
from constant.Const import ConstViewType, ConstFlag
from device.DeviceManager import DeviceManager
from device.uiview.FindUIInfo import FindUITargetInfo
from launch.AppLaunch import AppLaunch


def test_run(device: DeviceManager, app: DouYinApp):
    def snapshot():
        info = FindUITargetInfo(ConstViewType.Group, size=(0.915, 0.1389), position=(0.5, 0.1794),
                                parent_name=ConstViewType.Group, z_orders={'global': 0, 'local': 1})
        ui = device.exist_by_flag(info)
        if ui is not None:
            device.screenshot(save_path="app/douyin/337.jpg", ui=ui, quality=1)

    def example():
        second_ad_enter = device.exist_by_flag(
            FindUITargetInfo(ConstViewType.Group, size=(0.7583, 0.3928), position=(0.5, 0.4632),
                             z_orders={'global': 0, 'local': 3}, parent_name=ConstViewType.Frame))
        if second_ad_enter and isinstance(second_ad_enter, UIObjectProxy):
            x, y = second_ad_enter.get_position()
            xn, yn = device.get_touch_position_offset((x, y + 0.57))
            device.touch(xn, yn)
        # second_ad_enter.click(focus=)

    # if view:
    #     view.click()


# AppLaunch(callback=lambda device, app: test_run(device, app))
AppLaunch()
