import random
import time
from abc import abstractmethod, ABC


class DeviceRandomConfig(ABC):

    def __init__(self, level: int = 1):
        self.duration_level = level

    @abstractmethod
    def get_screen_size(self) -> tuple[int, int]:
        raise NotImplementedError()

    def sleep_operation_random(self):
        time.sleep(random.uniform(0.5, 3.5))

    def sleep_task_random(self, duration: float):
        diff = duration * 0.2
        time.sleep(random.uniform(duration, duration + diff))

    def _get_random_duration(self) -> float:
        return random.uniform(0.01, 0.1)

    def _get_click_timeout(self) -> float:
        return random.uniform(0.5, 2.8)

    def get_touch_duration(self) -> float:
        return self.duration_level * self._get_random_duration()

    def get_click_wait_time(self, level=1) -> float:
        return level * self._get_click_timeout()

    def get_click_position_offset(self) -> tuple[float, float]:
        x = random.uniform(0.03, 0.97)
        y = random.uniform(0.03, 0.97)
        return x, y

    def get_touch_position_offset(self, pos: tuple[float, float]) -> tuple[float, float]:
        x = pos[0] + random.uniform(-8, 8)
        y = pos[1] + random.uniform(-8, 8)
        return x, y

    def _get_swipe_vertical_random_x(self) -> float:
        screen_size = self.get_screen_size()
        width, height = screen_size
        return width // random.uniform(1.5, 2.5)

    def _get_swipe_vertical_random_y_start(self, is_up: bool) -> float:
        screen_size = self.get_screen_size()
        width, height = screen_size
        if is_up:
            return height * random.uniform(0.68, 0.83)
        else:
            return height * random.uniform(0.23, 0.38)

    def _get_swipe_vertical_random_y_end(self, is_up: bool) -> float:
        screen_size = self.get_screen_size()
        width, height = screen_size
        if is_up:
            return height * random.uniform(0.23, 0.38)
        else:
            return height * random.uniform(0.68, 0.83)

    def _get_swipe_horizontal_random_y(self) -> float:
        screen_size = self.get_screen_size()
        width, height = screen_size
        return height // random.uniform(1.5, 2.5)

    def _get_swipe_horizontal_random_x_start(self, is_left: bool) -> float:
        screen_size = self.get_screen_size()
        width, height = screen_size
        if is_left:
            return width * random.uniform(0.68, 0.83)
        else:
            return width * random.uniform(0.23, 0.38)

    def _get_swipe_horizontal_random_x_end(self, is_left: bool) -> float:
        screen_size = self.get_screen_size()
        width, height = screen_size
        if is_left:
            return width * random.uniform(0.23, 0.38)
        else:
            return width * random.uniform(0.68, 0.83)

    def _get_swipe_random_duration(self) -> float:
        return random.uniform(0.15, 0.5)
