import os
from pathlib import Path
from time import sleep

from airtest.core.android.android import Android
from airtest.core.api import wait
from airtest.core.error import TargetNotFoundError
from airtest.core.cv import Template
from airtest.core.helper import G

from poco.drivers.android.uiautomation import AndroidUiautomationPoco
from poco.proxy import UIObjectProxy

from device.config.DeviceRandomConfig import DeviceRandomConfig
from device.DeviceInfo import DeviceInfo
from logevent.DeviceRunningLog import DeviceRunningLog
from logevent.Log import Log


class DeviceBase(DeviceRandomConfig):
    dev: Android  # Android(serial="192.168.1.100:5555")
    poco: AndroidUiautomationPoco
    logEvent: DeviceRunningLog

    default_wait_view_timeout = 8
    _project_root: Path | None = None  # 缓存项目根目录

    screen_size = None

    def __init__(self, device_info: DeviceInfo):
        super(DeviceBase, self).__init__(level=1)
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

    def get_screen_size(self) -> tuple[int, int]:
        if self.screen_size is None:
            screen_size = self.poco.get_screen_size()
            self.screen_size = screen_size
        return self.screen_size

    def init_device(self):
        if self.dev.is_locked():
            self.dev.unlock()
            sleep(1.5)
            self.swipe_up_unlock()
            sleep(1.5)
        else:
            print("unlock")

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
        self.dev.keyevent("BACK")
        sleep(self.sleep_operation_random())

    def press_app_switch(self):
        self.dev.keyevent("APP_SWITCH")

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
            print("当前顶部activity", list)
            if len(list) == 2:
                return list[0], list[1]
            return act_name, ""
        except Exception as e:
            print(f"获取当前应用包名失败: {e}")
            return "", ""

    def is_app_running(self, package_name: str) -> bool:
        return self.get_top_activity()[0] == package_name

    @classmethod
    def _find_project_root(cls) -> Path:
        if cls._project_root is not None:
            return cls._project_root

        current_path = Path(__file__).resolve()

        for parent in [current_path] + list(current_path.parents):
            resource_dir = parent / "resource"
            if resource_dir.exists() and resource_dir.is_dir():
                cls._project_root = parent
                return parent

        fallback_root = current_path.parent.parent
        cls._project_root = fallback_root
        return fallback_root

    def get_resource_path(self, relative_path: str) -> str:
        project_root = self._find_project_root()
        resource_dir = project_root / "resource"
        resource_path = resource_dir / relative_path
        return str(resource_path.resolve())

    def get_view_attr(self, ui: UIObjectProxy, attr_name: str) -> str:
        """
        zOrders,boundsInParent
        """
        try:
            return ui.attr(attr_name)
        except Exception as e:
            return ""

    def flag_is_id(self, flag: str) -> bool:
        return flag.startswith("com.")

    def flag_is_image(self, flag: str) -> bool:
        return flag.lower().endswith(".png") or flag.lower().endswith(".jpg") or flag.lower().endswith(".jpeg")

    def __execute_exist_by_flag(self, flag: str, element: UIObjectProxy | None) -> UIObjectProxy | None:
        try:
            exist = element.exists()
            Log.d_view_exists(flag + ",是否存在:" + str(exist))
            if exist:
                return element
            return None
        except Exception as e:
            Log.d_view_exists(flag + ",查找异常：" + e)
            return None

    def exist_by_id(self, resource_id: str, timeout=default_wait_view_timeout) -> UIObjectProxy | None:
        try:
            element = self.poco(resourceId=resource_id).wait(timeout=timeout)
            return self.__execute_exist_by_flag(resource_id, element)
        except Exception as e:
            Log.d_view_exists("id:" + resource_id + "，异常：" + e)
            return None

    def exist_by_name(self, resource_name: str, timeout=default_wait_view_timeout) -> UIObjectProxy | None:
        try:
            element = self.poco(name=resource_name).wait(timeout=timeout)
            return self.__execute_exist_by_flag(resource_name, element)
        except Exception as e:
            Log.d_view_exists("name:" + resource_name + "，异常：" + e)
            return None

    def exist_by_text(self, text: str, timeout=default_wait_view_timeout) -> UIObjectProxy | None:
        try:
            element = self.poco(text=text).wait(timeout=timeout)
            return self.__execute_exist_by_flag(text, element)
        except Exception as e:
            Log.d_view_exists("text:" + text + "，异常：" + e)
            return None

    def exist_by_desc(self, desc: str, timeout=default_wait_view_timeout) -> UIObjectProxy | None:
        try:
            element = self.poco(desc=desc).wait(timeout=timeout)
            return self.__execute_exist_by_flag(desc, element)
        except Exception as e:
            Log.d_view_exists("desc:" + desc + "，异常：" + e)
            return None

    def exist_by_image(self, image_path: str, threshold=0.75, timeout: float = default_wait_view_timeout) -> tuple[
                                                                                                                 float, float] | None:
        try:
            abs_path = str(Path(self.get_resource_path(image_path)).resolve())
            if not os.path.exists(abs_path):
                Log.d_view_exists(f"图片文件不存在: {abs_path}")
                return None
            template = Template(abs_path, threshold=threshold)
            try:
                result = wait(template, timeout=timeout)
                Log.d_view_exists(f"image:{image_path},是否存在:True,位置:{result}")
                if result and isinstance(result, tuple):
                    return self.get_touch_position_offset(result)
                return None
            except TargetNotFoundError:
                Log.d_view_exists(f"image:{image_path},是否存在:False(超时{timeout}秒)")
                return None
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            Log.d_view_exists(f"图片异常: {image_path}, 错误: {str(e)}, 详情: {error_detail}")
            return None

    def exist_by_flag(self, flag: str, timeout: float = default_wait_view_timeout) -> bool:
        if self.flag_is_id(flag):
            if self.exist_by_id(flag, timeout=timeout):
                return True
        elif self.flag_is_image(flag):
            if self.exist_by_image(flag, timeout=timeout):
                return True
        else:
            if not self.exist_by_text(flag, timeout=timeout):
                if self.exist_by_desc(flag, timeout=1):
                    return True
            else:
                return True
        return False

    def __execute_click(self, flag: str, element: UIObjectProxy | None, double_check: bool = False) -> bool:
        if element is not None:
            sleep(self.get_click_wait_time())
            result = element.click(focus=self.get_click_position_offset())
            if double_check:
                element.click(focus=self.get_click_position_offset())
            Log.d_view_click(flag + ",click:" + str(result))
            if result is None or result:
                return True
        return False

    def click_by_id(self, resource_id: str, timeout=default_wait_view_timeout, double_check: bool = False) -> bool:
        element = self.exist_by_id(resource_id, timeout=timeout)
        return self.__execute_click(resource_id, element, double_check=double_check)

    def click_by_name(self, name: str, timeout=default_wait_view_timeout, double_check: bool = False) -> bool:
        element = self.exist_by_name(name, timeout=timeout)
        return self.__execute_click(name, element, double_check=double_check)

    def click_by_text(self, text: str, timeout=default_wait_view_timeout, double_check: bool = False) -> bool:
        element = self.exist_by_text(text, timeout=timeout)
        return self.__execute_click(text, element, double_check=double_check)

    def click_by_desc(self, desc: str, timeout=default_wait_view_timeout, double_check: bool = False) -> bool:
        element = self.exist_by_desc(desc, timeout=timeout)
        return self.__execute_click(desc, element, double_check=double_check)

    def click_by_image(self, image_path: str, threshold: float = 0.8,
                       timeout: float = default_wait_view_timeout) -> bool:
        position = self.exist_by_image(image_path, threshold=threshold, timeout=timeout)
        if position is not None:
            sleep(self.get_click_wait_time())
            self.dev.touch(pos=self.get_touch_position_offset(), duration=self.get_touch_duration())
            return True
        # touch() 支持 timeout 参数
        # touch(template, timeout=timeout)
        return False

    def click_by_flag(self, flag: str, timeout=default_wait_view_timeout) -> bool:
        if self.flag_is_id(flag):
            return self.click_by_id(flag, timeout=timeout)
        elif self.flag_is_image(flag):
            return self.click_by_image(flag, timeout=timeout)
        else:
            if not self.click_by_text(flag, timeout=timeout):
                return self.click_by_desc(flag, timeout=1)
            else:
                return True

    def is_text_selected(self, text: str) -> bool:
        ui = self.exist_by_text(text)
        if ui:
            selected = ui.attr("selected")
            print(text, "是否选中", selected)
            return selected
        return False

    def swipe_up(self, level=1):
        start_x = self._get_swipe_vertical_random_x()
        start_y = self._get_swipe_vertical_random_y_start(is_up=True)
        end_x = self._get_swipe_vertical_random_x()
        end_y = self._get_swipe_vertical_random_y_end(is_up=True)
        self.dev.swipe((start_x, start_y), (end_x, end_y), duration=self._get_swipe_random_duration())
        sleep(0.7)
        Log.d_swipe("向上滑动:" + str(end_y - start_y))

    def swipe_down(self, level=1):
        start_x = self._get_swipe_vertical_random_x()
        start_y = self._get_swipe_vertical_random_y_start(is_up=False)
        end_x = self._get_swipe_vertical_random_x()
        end_y = self._get_swipe_vertical_random_y_end(is_up=False)
        self.dev.swipe((start_x, start_y), (end_x, end_y), duration=self._get_swipe_random_duration())
        sleep(0.7)
        Log.d_swipe("向下滑动:" + str(end_y - start_y))

    def swipe_left(self, level=1):
        start_x = self._get_swipe_horizontal_random_x_start(True)
        start_y = self._get_swipe_horizontal_random_y()
        end_x = self._get_swipe_horizontal_random_x_end(True)
        end_y = self._get_swipe_horizontal_random_y()
        self.dev.swipe((start_x, start_y), (end_x, end_y), duration=self._get_swipe_random_duration())

    def swipe_right(self, level=1):
        start_x = self._get_swipe_horizontal_random_x_start(False)
        start_y = self._get_swipe_horizontal_random_y()
        end_x = self._get_swipe_horizontal_random_x_end(False)
        end_y = self._get_swipe_horizontal_random_y()
        self.dev.swipe((start_x, start_y), (end_x, end_y), duration=self._get_swipe_random_duration())
