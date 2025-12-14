from abc import ABC, abstractmethod

from app.douyin.DouYinApp import DouYinApp
from app.kuaishou.KuaiShouApp import KuaiShouApp
from constant.Const import ConstViewType, ConstFlag
from device.DeviceManager import DeviceManager
from device.uiview.UIInfo import UITargetInfo
from launch.AppLaunch import AppLaunch


def test_run(device: DeviceManager, app: DouYinApp):
    app.start_video_task()

    # if view:
    #     view.click()


AppLaunch(callback=lambda device, app: test_run(device, app))
# AppLaunch()
