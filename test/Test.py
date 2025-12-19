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
    # app.change_skip_home_task_page(True)
    # app.start_video_task()
    ui = FindUITargetInfo(ConstViewType.Group, size=(0.915, 0.1917), z_orders={'global': 0, 'local': 1},
                          parent_name=ConstViewType.Group,offset_x=0.3, offset_y=-0.3,
                          desc="")
    print(device.click_by_flag(ui))


# AppLaunch(callback=lambda device, app: test_run(device, app))
AppLaunch()
