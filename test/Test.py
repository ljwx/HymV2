from device.DeviceManager import DeviceManager
from launch.AppLaunch import AppLaunch


def test_run(device: DeviceManager):
    view = device.exist_by_id("com.kuaishou.nebula:id/plc_tv_biz_text")
    # if view:
    #     view.click()


AppLaunch(callback=lambda device: test_run(device))
# AppLaunch()