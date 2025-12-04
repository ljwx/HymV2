from poco.proxy import UIObjectProxy
from airtest.core.api import Template, exists, touch

from device.DeviceBase import DeviceBase
from device.DeviceInfo import DeviceInfo


class DeviceFindView(DeviceBase):
    def __init__(self, device_info: DeviceInfo):
        super().__init__(device_info)

    def _get_position_by_id(self, resource_id: str, timeout=10) -> tuple[float, float] | None:
        if self.exist_by_id(resource_id, timeout=timeout):
            element = self.poco(resourceId=resource_id)
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
