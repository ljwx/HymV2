import random

from poco.proxy import UIObjectProxy

from constant.Const import ConstViewType
from device.DeviceBase import DeviceBase
from device.DeviceInfo import DeviceInfo
from device.uiview.UIInfo import UITargetInfo


class DeviceFindView(DeviceBase):
    def __init__(self, device_info: DeviceInfo):
        super().__init__(device_info)

    def _get_position_by_id(self, resource_id: str, timeout=10) -> tuple[float, float] | None:
        element = self.exist_by_id(resource_id, timeout=timeout)
        if element is not None:
            position = element.get_position()
            return position
        return None

    def _get_position_by_name(self, name: str, timeout=10) -> tuple[float, float] | None:
        if self.exist_by_name(name, timeout=timeout):
            element = self.poco(name=name)
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
            element = self.poco(desc=desc)
            position = element.get_position()
            return position
        return None

    def click_position_diff_by_id(self, resource_id: str, post: tuple[float, float], timeout=10) -> bool:
        position = self._get_position_by_id(resource_id, timeout=timeout)
        if position is None:
            return False
        x = post[0] + position[0]
        y = post[1] + position[1]
        return self.poco.click([x, y])

    def click_position_diff_by_text(self, text: str, post: tuple[float, float], timeout=10) -> bool:
        position = self._get_position_by_text(text, timeout=timeout)
        if position is None:
            return False
        x = post[0] + position[0]
        y = post[1] + position[1]
        return self.poco.click([x, y])

    def find_child_form_parent_by_id(self, parent_id: str, child_index: int, timeout=10) -> UIObjectProxy | None:
        try:
            parent = self.poco(resourceId=parent_id).wait(timeout=timeout)
            if parent.exists():
                children = parent.children()
                if len(children) > child_index:
                    return children[child_index]
        except Exception as e:
            print(e)
        return None

    def find_view_from_offspring_by_id(self, parent_id: str, child_id: str, timeout=10) -> UIObjectProxy | None:
        try:
            parent = self.poco(resourceId=parent_id).wait(timeout=timeout)
            parent.get_bounds()
            if parent.exists():
                offspring = parent.offspring(resourceId=child_id)
                if offspring.exists():
                    return offspring
        except Exception as e:
            print(f"{e}")
        return None

    def __size_match(self, ui_size: tuple[float, float], info_size: tuple[float, float]) -> bool:
        size_diff = 0.05
        width = abs(ui_size[0] - info_size[0]) < size_diff
        height = abs(ui_size[1] - info_size[1]) < size_diff
        return width and height

    def __position_match(self, screen_position: tuple[float, float], target_position: tuple[float, float]) -> bool:
        position_diff = 0.09
        x = abs(screen_position[0] - target_position[0]) < position_diff
        y = abs(screen_position[1] - target_position[1]) < position_diff
        return x and y

    def find_ui_by_info(self, ui_info: UITargetInfo, timeout=3) -> UIObjectProxy | None:
        types = self.poco(type=ui_info.ui_name).wait(timeout=timeout)
        for type in types:
            size_match = True
            position_match = True
            parent_match = True
            if ui_info.size is not None:
                if not self.__size_match(type.get_size(), ui_info.size):
                    size_match = False
            if ui_info.position is not None:
                if not self.__position_match(type.get_position(), ui_info.position):
                    position_match = False
            if ui_info.parent_name is not None:
                parent = types.parent()
                if not parent.exists() or not parent.get_name() == ui_info.parent_name:
                    parent_match = False
            if size_match and position_match and parent_match:
                return type
        return None

    def find_ui_and_click(self, ui_info: UITargetInfo, timeout=3) -> bool:
        ui = self.find_ui_by_info(ui_info, timeout=timeout)
        if ui:
            ui.click(focus=self.get_click_position_offset())
            return True
        else:
            return False

    def example(self):
        self.find_ui_and_click(
            UITargetInfo(ConstViewType.Text, size=(0.1733, 0.0262), parent_name=ConstViewType.Linear))

    def find_all_contain_text(self, view_type: str, text: str, timeout=3) -> UIObjectProxy | None:
        types = self.poco(type=view_type).wait(timeout=timeout)
        if not types:
            return None
        for ui in types:
            ui_text = ui.get_text()
            if ui_text and text in ui_text:
                print(ui_text)
                return ui
        return None

    def find_list_by_flag(self, flag: str, timeout=3) -> UIObjectProxy | None:
        if flag.__contains__("com."):
            types = self.poco(name=flag).wait(timeout=timeout)
            if types and len(types) > 0:
                index = random.randint(0, len(types) - 1)
                return types[index]
        else:
            types = self.poco(text=flag).wait(timeout=timeout)
            if types and len(types) > 0:
                index = random.randint(0, len(types) - 1)
                return types[index]
            else:
                types = self.poco(desc=flag).wait(timeout=timeout)
                if types and len(types) > 0:
                    index = random.randint(0, len(types) - 1)
                    return types[index]
        return None

    def find_list_by_child(self, flag: str, timeout=3) -> UIObjectProxy | None:
        try:
            parent = self.poco(resourceId=flag).wait(timeout=timeout)
            if parent.exists():
                children = parent.children()
                if children and len(children) > 0:
                    index = random.randint(0, len(children) - 1)
                    return children[index]
        except Exception as e:
            print("查找子view异常", e)
        return None
