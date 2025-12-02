import random


class DeviceDurationConfig:

    def __init__(self, level: int = 1):
        self.duration_level = level

    def _get_random_duration(self) -> float:
        return random.uniform(0.01, 0.1)

    def get_touch_duration(self) -> float:
        return self.duration_level * self._get_random_duration()

