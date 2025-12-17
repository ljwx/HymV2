import random

from poco.proxy import UIObjectProxy

from constant.Const import ConstViewType, ConstFlag
from device.DeviceBase import DeviceBase
from device.DeviceInfo import DeviceInfo
from device.uiview.FindUIInfo import FindUITargetInfo


class DeviceFindView(DeviceBase):
    def __init__(self, device_info: DeviceInfo):
        super().__init__(device_info)

    def _get_position_by_id(self, resource_id: str, timeout=10) -> tuple[float, float] | None:
        element = self.exist_by_id(resource_id, timeout=timeout)
        if element is not None:
            position = element.get_position()
            return position
        return None

    def _get_position_by_text(self, text: str, timeout=10) -> tuple[float, float] | None:
        if self.exist_by_text(text, timeout=timeout):
            element = self.poco(text=text)
            position = element.get_position()
            return position
        return None

    def _get_position_by_desc(self, desc: str, timeout=10) -> tuple[float, float] | None:
        if self.exist_by_desc(desc, timeout=timeout):
            element = self.poco(desc=desc.replace(ConstFlag.Desc, ""))
            position = element.get_position()
            return position
        return None

    def find_child_form_parent_by_id(self, parent_id: str, child_index: int, timeout=10) -> UIObjectProxy | None:
        try:
            parent = self.poco(resourceId=parent_id).wait(timeout=timeout)
            if parent is not None and parent.exists():
                children = parent.children()
                if len(children) > child_index:
                    return children[child_index]
        except Exception as e:
            print(e)
        return None

    def find_view_from_offspring_by_id(self, parent_id: str, child_id: str, timeout=10) -> UIObjectProxy | None:
        try:
            parent = self.poco(resourceId=parent_id).wait(timeout=timeout)
            if parent is None:
                return None
            parent.get_bounds()
            if parent.exists():
                offspring = parent.offspring(resourceId=child_id)
                if offspring is not None and offspring.exists():
                    return offspring
        except Exception as e:
            print(f"{e}")
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

    def exist_by_find_info(self, ui_info: FindUITargetInfo, timeout=3) -> UIObjectProxy | None:
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

    def click_by_find_info(self, ui_info: FindUITargetInfo, timeout=3) -> bool:
        ui = self.exist_by_find_info(ui_info, timeout=timeout)
        if ui is not None:
            ui.click(focus=self.get_click_position_offset())
            return True
        else:
            return False

    def example(self):
        self.click_by_find_info(
            FindUITargetInfo(ConstViewType.Text, size=(0.1733, 0.0262), parent_name=ConstViewType.Linear))

    def find_all_contain_text(self, view_type: str, text: str, timeout=3) -> UIObjectProxy | None:
        types = self.poco(type=view_type).wait(timeout=timeout)
        if types is None:
            return None
        for ui in types:
            ui_text = ui.get_text()
            if ui_text and text in ui_text:
                self.logd("找到了", ui_text)
                return ui
        return None

    def find_all_contain_name(self, view_type: str, text: str, timeout=3) -> UIObjectProxy | None:
        types = self.poco(type=view_type).wait(timeout=timeout)
        if types is None:
            return None
        for ui in types:
            ui_text = ui.get_name()
            if ui_text and text in ui_text:
                self.logd("找到了", ui_text)
                return ui
        return None

    def find_list_by_flag(self, flag: str, timeout=3) -> UIObjectProxy | None:
        if self.flag_is_id(flag):
            types = self.poco(name=flag).wait(timeout=timeout)
            if types is not None and len(types) > 0:
                index = random.randint(0, len(types) - 1)
                return types[index]
        elif self.flag_is_desc(flag):
            types = self.poco(desc=flag.replace(ConstFlag.Desc)).wait(timeout=timeout)
            if types is not None and len(types) > 0:
                index = random.randint(0, len(types) - 1)
                return types[index]
        else:
            types = self.poco(text=flag).wait(timeout=timeout)
            if types is not None and len(types) > 0:
                index = random.randint(0, len(types) - 1)
                return types[index]
        return None

    def __find_recycler_view(self, timeout) -> UIObjectProxy | None:
        ui = self.poco(type=ConstViewType.Recycler).wait(timeout=timeout)
        if ui is not None:
            return ui
        return None

    def find_list_by_child(self, flag: str, timeout=3) -> UIObjectProxy | None:
        try:
            parent = None
            if flag.__contains__("widget.RecyclerView"):
                ui = self.__find_recycler_view(timeout)
                if ui is not None:
                    parent = ui
            else:
                parent = self.poco(resourceId=flag).wait(timeout=timeout)
            if parent is not None and parent.exists():
                children = parent.children()
                if len(children) > 0:
                    index = random.randint(0, len(children) - 1)
                    return children[index]
        except Exception as e:
            self.logd("查找子view异常", str(e))
        return None
