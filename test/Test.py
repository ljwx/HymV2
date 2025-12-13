from app.kuaishou.KuaiShouApp import KuaiShouApp
from constant.Const import ConstViewType, ConstFlag
from device.DeviceManager import DeviceManager
from device.uiview.UIInfo import UITargetInfo
from launch.AppLaunch import AppLaunch


def test_run(device: DeviceManager, app: KuaiShouApp):
    app.device.exist_by_flag(ConstFlag.Desc+"close_view")


    # if view:
    #     view.click()


# AppLaunch(callback=lambda device, app: test_run(device, app))
AppLaunch()
