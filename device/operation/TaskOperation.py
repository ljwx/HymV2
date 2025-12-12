from typing import Callable, Any

from device.config.TaskRandomConfig import TaskRandomConfig
from logevent.Log import Log


class TaskOperation(TaskRandomConfig):
    def __init__(self):
        pass

    def main_task_range(self, callback: Callable[[], Any], test_times: int = None):
        times = self.get_main_task_count() if test_times is None else test_times
        Log.d("主任务次数", str(times))
        for i in range(times):
            callback()
