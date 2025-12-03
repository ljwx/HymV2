import random


class DeviceDurationConfig:

    def __init__(self, level: int = 1):
        self.duration_level = level

    def _get_random_duration(self) -> float:
        return random.uniform(0.01, 0.1)

    def _get_click_timeout(self) -> float:
        return random.uniform(0.5, 2.8)

    def get_touch_duration(self) -> float:
        return self.duration_level * self._get_random_duration()

    def get_click_wait_time(self) -> float:
        return self.duration_level * self._get_click_timeout()

    def get_click_position(self) -> tuple[float, float]:
        x = random.uniform(0.03, 0.97)
        y = random.uniform(0.03, 0.97)
        return x, y
