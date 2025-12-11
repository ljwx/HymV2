from device.DeviceManager import DeviceManager
from launch.AppLaunch import AppLaunch


def test_run(device: DeviceManager):
    view = device.press_back()
    # if view:
    #     view.click()


AppLaunch(callback=lambda device: test_run(device))
# AppLaunch()