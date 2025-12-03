import random

from device.DeviceConnect import DeviceConnect, DeviceInfo


class DeviceCommonOperation(DeviceConnect):
    def __init__(self, device_info: DeviceInfo):
        super().__init__(device_info)

    def _get_swipe_vertical_random_x(self) -> float:
        return random.uniform(1.5, 2.5)

    def _get_swipe_vertical_random_y_start(self, is_up: bool) -> float:
        if is_up:
            return random.uniform(0.68, 0.83)
        else:
            return random.uniform(0.23, 0.38)

    def _get_swipe_vertical_random_y_end(self, is_up: bool) -> float:
        if is_up:
            return random.uniform(0.23, 0.38)
        else:
            return random.uniform(0.68, 0.83)

    def swipe_up(self, level=1):
        screen_size = self.get_screen_size()
        width, height = screen_size

        start_x = width // self._get_swipe_vertical_random_x()
        start_y = int(height * self._get_swipe_vertical_random_y_start(is_up=True))
        end_x = width // self._get_swipe_vertical_random_x()
        end_y = int(height * self._get_swipe_vertical_random_y_end(is_up=True))

        self.dev.swipe((start_x, start_y), (end_x, end_y))

    def swipe_down(self, level=1):
        screen_size = self.get_screen_size()
        width, height = screen_size

        start_x = width // self._get_swipe_vertical_random_x()
        start_y = int(height * self._get_swipe_vertical_random_y_start(is_up=False))
        end_x = width // self._get_swipe_vertical_random_x()
        end_y = int(height * self._get_swipe_vertical_random_y_end(is_up=False))

        self.dev.swipe((start_x, start_y), (end_x, end_y))
