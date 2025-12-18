import ast
import os
import warnings
from abc import abstractmethod
from datetime import datetime
from pathlib import Path
from time import sleep

# 抑制 ADBCAP 效率警告（已知权衡：更隐蔽但更慢）
warnings.filterwarnings("ignore", message="Currently using ADB screenshots")

from PIL import Image
from airtest.core.android.android import Android
from airtest.core.api import wait
from airtest.core.error import TargetNotFoundError
from airtest.core.cv import Template
from airtest.core.helper import G

from poco.drivers.android.uiautomation import AndroidUiautomationPoco
from poco.proxy import UIObjectProxy

from constant.Const import ConstFlag
from device.config.DeviceRandomConfig import DeviceRandomConfig
from device.DeviceInfo import DeviceInfo
from device.uiview.FindUIInfo import FindUITargetInfo
from logevent.DeviceRunningLog import DeviceRunningLog
from logevent.Log import Log

COLOR_RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
COLOR_RESET = '\033[0m'  # 重置颜色


class DeviceBase(DeviceRandomConfig):
    dev: Android  # Android(serial="192.168.1.100:5555")
    poco: AndroidUiautomationPoco
    logEvent: DeviceRunningLog

    default_wait_view_timeout = 8
    _project_root: Path | None = None  # 缓存项目根目录
    debug_multiple_elements = False  # 调试开关：是否检查多元素匹配（会增加 RPC 耗时）

    screen_size = None

    def __init__(self, device_info: DeviceInfo):
        super(DeviceBase, self).__init__(level=1)
        self.device_info = device_info
        print("开始连接")
        self.device_ready = False
        try:
            self.dev = Android(
                serialno=device_info.serial_no,
                cap_method="ADBCAP"  # 使用系统原生截图，更隐蔽
            )
            # 将设备注册到 Airtest 全局设备管理器（poco 使用 use_airtest_input=True 时需要）
            G.DEVICE = self.dev
            self.poco = AndroidUiautomationPoco(
                device=self.dev,
                use_airtest_input=True,  # 启用Airtest输入（解决中文输入问题）
                screenshot_each_action=False  # 关闭每次操作自动截图（提升速度）
            )
            self.init_device()
            self.device_ready = True
        except Exception as e:
            print("设备连接异常", e)

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
        self.logd("点击返回键")
        self.dev.keyevent("BACK")
        self.sleep_operation_random()

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
            self.logd("当前顶部activity", list)
            if len(list) == 2:
                return list[0], list[1]
            return act_name, ""
        except Exception as e:
            self.logd(f"获取当前应用包名失败: {e}")
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

    def flag_is_desc(self, flag: str) -> bool:
        return flag.startswith(ConstFlag.Desc)

    def flag_is_position(self, flag: str) -> bool:
        return flag.startswith(ConstFlag.Position)

    def flag_is_find_info(self, flag: FindUITargetInfo) -> bool:
        return isinstance(flag, FindUITargetInfo)

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

    def _exist_by_id(self, resource_id: str, timeout=default_wait_view_timeout) -> UIObjectProxy | None:
        try:
            element = self.poco(resourceId=resource_id).wait(timeout=timeout)
            if self.debug_multiple_elements and len(element) > 1:
                for i in element:
                    self.logd("多个:" + resource_id, i.get_position())
            return self.__execute_exist_by_flag(resource_id, element)
        except Exception as e:
            Log.d_view_exists(f"{COLOR_RED}id:{resource_id}，异常：{e}{COLOR_RESET}")
            return None

    def _exist_by_text(self, text: str, timeout=default_wait_view_timeout) -> UIObjectProxy | None:
        if not isinstance(text, str):
            Log.d_view_exists(f"{COLOR_RED}exist_by_text 收到非字符串参数: {type(text)}{COLOR_RESET}")
            return None
        try:
            element = self.poco(text=text).wait(timeout=timeout)
            if self.debug_multiple_elements and len(element) > 1:
                for i in element:
                    self.logd("多个:" + text, i.get_position())
            return self.__execute_exist_by_flag(text, element)
        except Exception as e:
            Log.d_view_exists(f"{COLOR_RED}text:{text}，异常：{e}{COLOR_RESET}")
            return None

    def _exist_by_desc(self, desc: str, timeout=default_wait_view_timeout) -> UIObjectProxy | None:
        try:
            element = self.poco(desc=desc.replace(ConstFlag.Desc, "")).wait(timeout=timeout)
            if self.debug_multiple_elements and len(element) > 1:
                for i in element:
                    self.logd("多个desc:" + desc, i.get_position())
            return self.__execute_exist_by_flag(desc, element)
        except Exception as e:
            Log.d_view_exists(f"{COLOR_RED}desc:{desc}，异常：{e}{COLOR_RESET}")
            return None

    def _exist_by_image(self, image_path: str, threshold=0.75, timeout: float = default_wait_view_timeout) -> \
            tuple[float, float] | None:
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
            Log.d_view_exists(f"{COLOR_RED}图片异常: {image_path}, 错误: {str(e)}, 详情: {error_detail}{COLOR_RESET}")
            return None

    def __size_match(self, ui_size: tuple[float, float], info_size: tuple[float, float]) -> bool:
        size_diff = 0.075
        width = abs(ui_size[0] - info_size[0]) < size_diff
        height = abs(ui_size[1] - info_size[1]) < size_diff
        return width and height

    def __position_match(self, screen_position: tuple[float, float], target_position: tuple[float, float]) -> bool:
        position_diff = 0.09
        x = abs(screen_position[0] - target_position[0]) < position_diff
        y = abs(screen_position[1] - target_position[1]) < position_diff
        return x and y

    def _exist_by_find_info(self, ui_info: FindUITargetInfo, timeout=3) -> UIObjectProxy | None:
        types = self.poco(type=ui_info.ui_name).wait(timeout=timeout)
        if types is None:
            return None
        for type in types:
            size_match = True
            position_match = True
            parent_match = True
            z_orders_match = True
            content_match = True
            if ui_info.size is not None:
                if not self.__size_match(type.get_size(), ui_info.size):
                    size_match = False
            if ui_info.position is not None:
                if not self.__position_match(type.get_position(), ui_info.position):
                    position_match = False
            if ui_info.parent_name is not None:
                parent = type.parent()
                if not parent.exists() or not parent.attr("type") == ui_info.parent_name:
                    parent_match = False
            if ui_info.z_orders is not None:
                z_orders_match = False
                zord = type.attr("zOrders")
                if isinstance(zord, dict):
                    _global = zord.get("global") == ui_info.z_orders.get("global")
                    _local = zord.get("local") == ui_info.z_orders.get("local")
                    if _global and _local:
                        z_orders_match = True
            if ui_info.contains_text is not None:
                text = type.get_text()
                if text is not None and text.strip().__contains__(ui_info.contains_text):
                    content_match = True
                else:
                    content_match = False
            if size_match and position_match and parent_match and z_orders_match and content_match:
                self.logd("通过ui_info找到了ui", str(ui_info.desc) if ui_info.desc is not None else "")
                return type
            # if size_match and position_match:
            #     print(zord, type.parent().attr("type"))
        return None

    def exist_by_flag(self, flag: str | FindUITargetInfo,
                      timeout: float = default_wait_view_timeout) -> UIObjectProxy | None | tuple[float, float]:
        if self.flag_is_find_info(flag):
            ui = self._exist_by_find_info(flag, timeout=timeout)
            if ui is not None:
                return ui
        elif self.flag_is_id(flag):
            ui = self._exist_by_id(flag, timeout=timeout)
            if ui is not None:
                return ui
        elif self.flag_is_image(flag):
            ui = self._exist_by_image(flag, timeout=timeout)
            if ui is not None:
                return ui
        elif self.flag_is_desc(flag):
            ui = self._exist_by_desc(flag, timeout=timeout)
            if ui is not None:
                return ui
        elif isinstance(flag, str):
            ui = self._exist_by_text(flag, timeout=timeout)
            if ui is not None:
                return ui
        return None

    def __execute_click(self, flag: str, element: UIObjectProxy | None, double_check: bool = False) -> bool:
        if element is not None:
            result = element.click(focus=self.get_click_position_offset())
            if double_check:
                element.click(focus=self.get_click_position_offset())
            Log.d_view_click(flag + ",click:" + str(result))
            if result is None or result:
                return True
        return False

    def _click_by_id(self, resource_id: str, timeout=default_wait_view_timeout,
                     double_check: bool = False) -> bool:
        element = self._exist_by_id(resource_id, timeout=timeout)
        return self.__execute_click(resource_id, element, double_check=double_check)

    def _click_by_text(self, text: str, timeout=default_wait_view_timeout, double_check: bool = False) -> bool:
        element = self._exist_by_text(text, timeout=timeout)
        return self.__execute_click(text, element, double_check=double_check)

    def _click_by_desc(self, desc: str, timeout=default_wait_view_timeout, double_check: bool = False) -> bool:
        element = self._exist_by_desc(desc, timeout=timeout)
        return self.__execute_click(desc, element, double_check=double_check)

    def _click_by_image(self, image_path: str, threshold: float = 0.8,
                        timeout: float = default_wait_view_timeout) -> bool:
        position = self._exist_by_image(image_path, threshold=threshold, timeout=timeout)
        if position is not None:
            sleep(self.get_click_wait_time())
            self.dev.touch(pos=self.get_touch_position_offset(position), duration=self.get_touch_duration())
            return True
        # touch() 支持 timeout 参数
        # touch(template, timeout=timeout)
        return False

    def _click_by_find_info(self, ui_info: FindUITargetInfo, timeout=3) -> bool:
        ui = self._exist_by_find_info(ui_info, timeout=timeout)
        if ui is not None:
            ui.click(focus=self.get_click_position_offset())
            return True
        else:
            return False

    def click_by_flag(self, flag: str | FindUITargetInfo, timeout=default_wait_view_timeout) -> bool:
        if self.flag_is_find_info(flag):
            return self._click_by_find_info(flag, timeout=timeout)
        elif self.flag_is_id(flag):
            return self._click_by_id(flag, timeout=timeout)
        elif self.flag_is_image(flag):
            return self._click_by_image(flag, timeout=timeout)
        elif self.flag_is_desc(flag):
            return self._click_by_desc(flag, timeout=timeout)
        elif self.flag_is_position(flag):
            pos_str = flag.replace(ConstFlag.Position, "")
            pos = tuple(ast.literal_eval(pos_str))
            print("点击位置", pos)
            self.dev.touch(pos=self.get_touch_position_offset(pos), duration=self.get_touch_duration())
            return True
        elif isinstance(flag, str):
            return self._click_by_text(flag, timeout=timeout)
        return False

    def is_text_selected(self, text: str) -> bool:
        if not isinstance(text, str):
            return False
        ui = self._exist_by_text(text)
        if ui is not None:
            selected = ui.attr("selected")
            self.logd(text, "是否选中", selected)
            return selected
        return False

    def swipe_up(self):
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

    def logd(self, *content):
        now = datetime.now()
        formatted_time = now.strftime("%Y-%m-%d %H:%M:%S")
        print(Log.filter, formatted_time, *content)

    def screenshot(self, save_path: str = None, ui: UIObjectProxy = None,
                   quality: int = 5, scale: float = 0.2) -> Image.Image | None:
        """
        截图：传 ui 则按元素区域裁剪，否则全屏
        Args:
            save_path: 相对路径如 "base/111.jpg"，自动存到项目目录下（推荐用 .jpg 可压缩）
            ui: 元素对象（可选），传则裁剪该元素区域
            quality: 截图质量 1-100，默认 10（仅对 JPEG 格式有效）
            scale: 缩放比例 0.1-1.0，默认 0.4（越小文件越小，0.4 表示缩小到 40%）
        """
        try:
            self.logd("开始截图", save_path if save_path else "")
            raw = self.dev.snapshot()
            if raw is None:
                return None
            img = Image.fromarray(raw)

            # 缩放图片（提升处理速度）
            if scale < 1.0:
                new_size = (int(img.width * scale), int(img.height * scale))
                img = img.resize(new_size, Image.Resampling.LANCZOS)

            if ui is not None:
                try:
                    top, right, bottom, left = ui.get_bounds()
                    w, h = img.size
                    x0, y0 = int(left * w), int(top * h)
                    x1, y1 = int(right * w), int(bottom * h)
                    if x1 > x0 and y1 > y0:
                        img = img.crop((x0, y0, x1, y1))
                    else:
                        self.logd(f"裁剪坐标无效: ({x0},{y0}) -> ({x1},{y1})，返回全屏截图")
                except Exception as e:
                    self.logd(f"获取元素边界失败: {e}，返回全屏截图")
            if save_path:
                full = self._find_project_root() / save_path
                full.parent.mkdir(parents=True, exist_ok=True)
                # JPEG 格式支持 quality 压缩，PNG 是无损格式不支持
                if save_path.lower().endswith(('.jpg', '.jpeg')):
                    img.save(str(full), quality=quality)
                else:
                    img.save(str(full))
            self.logd("截图完成", save_path if save_path else "")
            return img
        except Exception as e:
            self.logd(f"截图异常: {e}")
            return None
