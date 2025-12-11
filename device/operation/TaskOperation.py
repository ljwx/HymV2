from typing import Callable, Any

from device.config.TaskRandomConfig import TaskRandomConfig


class TaskOperation(TaskRandomConfig):
    def __init__(self):
        pass

    def main_task_range(self, callback: Callable[[], Any], test_times: int = None):
        for i in range(self.get_main_task_count() if test_times is None else test_times):
            callback()
