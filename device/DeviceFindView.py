import random

from poco.proxy import UIObjectProxy

from constant.Const import ConstViewType, ConstFlag
from device.DeviceBase import DeviceBase
from device.DeviceInfo import DeviceInfo
from device.uiview.FindUIInfo import FindUITargetInfo


class DeviceFindView(DeviceBase):
    def __init__(self, device_info: DeviceInfo):
        super().__init__(device_info)

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
