from time import sleep
from airtest.core.android.android import Android

from poco.drivers.android.uiautomation import AndroidUiautomationPoco

from device.DeviceDurationConfig import DeviceDurationConfig
from logevent.DeviceRunningLog import DeviceRunningLog


class DeviceInfo:
    def __init__(self, serial):
        self.serial_no = serial


class DeviceConnect(DeviceDurationConfig):
    dev: Android  # Android(serial="192.168.1.100:5555")
    poco: AndroidUiautomationPoco
    logEvent: DeviceRunningLog

    def __init__(self, device_info: DeviceInfo):
        super(DeviceConnect, self).__init__(level=1)
        self.device_info = device_info
        print("开始连接")
        self.dev = Android(serialno=device_info.serial_no)
        self.poco = AndroidUiautomationPoco(
            device=self.dev,
            use_airtest_input=True,  # 启用Airtest输入（解决中文输入问题）
            screenshot_each_action=False  # 关闭每次操作自动截图（提升速度）
        )
        sleep(3)
        self.init_device()

    def get_screen_size(self):
        screen_size = self.poco.get_screen_size()
        return screen_size

    def init_device(self):
        if self.dev.is_locked():
            self.dev.unlock()
            sleep(1.5)
            self.swipe_up_unlock()
        else:
            print()

    def swipe_up_unlock(self):
        screen_size = self.get_screen_size()
        width, height = screen_size

        start_x = width // 2
        start_y = int(height * 0.8)
        end_x = width // 2
        end_y = int(height * 0.2)

        self.dev.swipe((start_x, start_y), (end_x, end_y))

    def start_app(self, package_name: str):
        if self.is_app_exist(package_name):
            self.dev.start_app(package_name)
        else:
            self.dev.start_app(package_name)

    def stop_app(self, package_name: str):
        self.dev.stop_app(package_name)

    def press_home(self):
        self.dev.home()

    def press_back(self):
        self.dev.keyevent("HOME")

    def press_menu(self):
        self.dev.keyevent("MENU")

    def press_volume_up(self):
        self.dev.keyevent("VOLUME_UP")

    def press_volume_down(self):
        self.dev.keyevent("VOLUME_DOWN")

    def press_power(self):
        self.dev.keyevent("POWER")

    def device_wake(self):
        self.dev.wake()

    def touch(self, x, y):
        self.dev.touch((x, y), duration=self.get_touch_duration())

    def is_screen_on(self) -> bool:
        return self.dev.is_screenon()

    def is_app_exist(self, package_name: str) -> bool:
        return self.dev.check_app(package_name)
