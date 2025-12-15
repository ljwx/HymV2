from typing import Callable, Any

from device.config.TaskRandomConfig import TaskRandomConfig
from logevent.Log import Log

COLOR_RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
COLOR_RESET = '\033[0m'  # 重置颜色


class TaskOperation(TaskRandomConfig):
    def __init__(self):
        pass

    def main_task_range(self, callback: Callable[[], Any], test_times: int = None):
        times = self.get_main_task_count() if test_times is None else test_times
        Log.d("主任务次数", str(times))
        for i in range(times):
            callback()
            Log.d("主任务次数", f"{COLOR_RED}主任务次数剩:{str(times - i - 1)}{COLOR_RESET}")
