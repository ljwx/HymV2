from time import sleep
from airtest.core.android.android import Android

from poco.drivers.android.uiautomation import AndroidUiautomationPoco


class DeviceInfo:
    def __init__(self, serial):
        self.serial_no = serial


class DeviceConnect:
    dev = Android  # Android(serial="192.168.1.100:5555")
    poco = AndroidUiautomationPoco

    def __init__(self, device_info: DeviceInfo):
        self.device_info = device_info
        self.dev = Android(serialno=device_info.serial_no)
        self.poco = AndroidUiautomationPoco(
            device=self.dev,
            use_airtest_input=True,  # 启用Airtest输入（解决中文输入问题）
            screenshot_each_action=False  # 关闭每次操作自动截图（提升速度）
        )

        sleep(3)
        self.connect()

    def connect(self):
        screen_size = self.poco.get_screen_size()
        print(f"设备屏幕尺寸：{screen_size}")  # 输出示例：(1080, 2400)

        self.dev.start_app("com.codemao.toolssdk")  # 启动计算器
        # poco.stop_app("com.android.calculator2")  # 关闭计算器

    def pressHome(self):
        self.dev.press_home()

    def pressBack(self):
        self.dev.press_back()

    def screenOn(self):
        self.dev.screen_on()

    def screenOff(self):
        self.dev.screen_off()


DeviceConnect(DeviceInfo("NAB0220416035468"))
