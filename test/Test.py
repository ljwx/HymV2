from device.DeviceManager import DeviceManager
from launch.AppLaunch import AppLaunch


def test_run(device: DeviceManager):
    view = device.exist_by_text("任务中心")
    # if view:
    #     view.click()


# AppLaunch(callback=lambda device: test_run(device))
AppLaunch()