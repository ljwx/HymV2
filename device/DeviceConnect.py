from time import sleep
from airtest.core.android.android import Android
from airtest.core.helper import G

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
        # 将设备注册到 Airtest 全局设备管理器（poco 使用 use_airtest_input=True 时需要）
        G.DEVICE = self.dev
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
        self.dev.get_top_activity_name()
        return self.dev.check_app(package_name)

    def get_current_package(self) -> str:
        try:
            # 方法1：使用 dumpsys window 命令
            output = self.dev.shell("dumpsys window windows | grep -E 'mCurrentFocus|mFocusedApp'")
            if output:
                # 解析输出，提取包名
                # 输出格式类似：mCurrentFocus=Window{xxx u0 com.example.app/.MainActivity}
                lines = output.strip().split('\n')
                for line in lines:
                    if 'mCurrentFocus' in line or 'mFocusedApp' in line:
                        # 提取包名部分
                        parts = line.split()
                        for part in parts:
                            if '/' in part:
                                package = part.split('/')[0]
                                # 清理可能的特殊字符
                                package = package.split('{')[-1] if '{' in package else package
                                if package.startswith('com.'):
                                    return package
            return ""
        except Exception as e:
            print(f"获取当前应用包名失败: {e}")
            return ""

    def is_app_running(self, package_name: str) -> bool:
        current_package = self.get_current_package()
        return current_package == package_name

    def wait_for_app(self, package_name: str, timeout: int = 10) -> bool:
        import time
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.is_app_running(package_name):
                return True
            sleep(0.5)
        return False

    def exist_by_id(self, resource_id: str) -> bool:
        return self.poco(resourceId=resource_id).wait().exists()

    def exist_by_name(self, resource_name: str) -> bool:
        return self.poco(name=resource_name).wait().exists()

    def exist_by_text(self, resource_text: str) -> bool:
        return self.poco(text=resource_text).wait().exists()

    def click_by_id(self, resource_id: str):
        self.poco(resourceId=resource_id).click()

    def click_by_name(self, name: str):
        self.poco(name=name).click()

    def click_by_text(self, text: str):
        # todo待确认
        self.poco(text=text).click()

    def click_by_desc(self, desc: str):
        self.poco(desc=desc).click()
