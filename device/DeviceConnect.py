from time import sleep
from airtest.core.android.android import Android
from airtest.core.helper import G

from poco.drivers.android.uiautomation import AndroidUiautomationPoco

from device.DeviceDurationConfig import DeviceDurationConfig
from device.DeviceInfo import DeviceInfo
from logevent.DeviceRunningLog import DeviceRunningLog


class DeviceConnect(DeviceDurationConfig):
    dev: Android  # Android(serial="192.168.1.100:5555")
    poco: AndroidUiautomationPoco
    logEvent: DeviceRunningLog

    default_wait_view_timeout = 10

    def __init__(self, device_info: DeviceInfo):
        super(DeviceConnect, self).__init__(level=1)
        self.device_info = device_info
        print("开始连接")
        self.dev = Android(serialno=device_info.serial_no)
        # 将设备注册到 Airtest 全局设备管理器（poco 使用 use_airtest_input=True 时需要）
        G.DEVICE = self.dev
        self.poco = AndroidUiautomationPoco(
            device=self.dev,
            use_airtest_input=True,  # 启用Airtest输入（解决中文输入问题）
            screenshot_each_action=False  # 关闭每次操作自动截图（提升速度）
        )
        self.init_device()

    def get_screen_size(self):
        screen_size = self.poco.get_screen_size()
        return screen_size

    def init_device(self):
        if self.dev.is_locked():
            self.dev.unlock()
            sleep(1.5)
            self.swipe_up_unlock()
            sleep(1.5)
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
        self.dev.get_top_activity_name()
        return self.dev.check_app(package_name)

    def get_top_activity(self) -> tuple:
        try:
            act_name = self.dev.get_top_activity_name()
            list = act_name.split("/.")
            if len(list) == 1:
                list = act_name.split("/")
            print(list)
            if len(list) == 2:
                return list[0], list[1]
            return act_name, ""
        except Exception as e:
            print(f"获取当前应用包名失败: {e}")
            return "", ""

    def is_app_running(self, package_name: str) -> bool:
        return self.get_top_activity()[0] == package_name

    def exist_by_id(self, resource_id: str, timeout=default_wait_view_timeout) -> bool:
        return self.poco(resourceId=resource_id).wait(timeout=timeout).exists()

    def exist_by_name(self, resource_name: str, timeout=default_wait_view_timeout) -> bool:
        return self.poco(name=resource_name).wait(timeout=timeout).exists()

    def exist_by_text(self, text: str, timeout=default_wait_view_timeout) -> bool:
        return self.poco(text=text).wait(timeout=timeout).exists()

    def exist_by_desc(self, desc: str, timeout=default_wait_view_timeout) -> bool:
        return self.poco(desc=desc).wait(timeout=timeout).exists()

    def click_by_id(self, resource_id: str, timeout=default_wait_view_timeout) -> bool:
        if self.exist_by_id(resource_id, timeout=timeout):
            sleep(self.get_click_wait_time())
            result = self.poco(resourceId=resource_id).click(focus=self.get_click_position())
            if result is None or result:
                return True
        return False

    def click_by_name(self, name: str, timeout=default_wait_view_timeout) -> bool:
        if self.exist_by_name(name, timeout=timeout):
            sleep(self.get_click_wait_time())
            result = self.poco(name=name).click(focus=self.get_click_position())
            if result is None or result:
                return True
        return False

    def click_by_text(self, text: str, timeout=default_wait_view_timeout) -> bool:
        if self.exist_by_text(text, timeout=timeout):
            sleep(self.get_click_wait_time())
            result = self.poco(text=text).click()
            if result is None or result:
                return True
        return False

    def click_by_desc(self, desc: str, timeout=default_wait_view_timeout) -> bool:
        if self.exist_by_desc(desc, timeout=timeout):
            sleep(self.get_click_wait_time())
            result = self.poco(desc=desc).click(focus=self.get_click_position())
            if result is None or result:
                return True
        return False
