import random


class TaskRandomConfig:
    def __init__(self):
        pass

    def get_main_task_count(self, rate=1) -> int:
        min = int(rate * 5)
        max = int(rate * 26)
        main_task_count = random.randint(min, max)
        print("主任务次数", main_task_count)
        return main_task_count

    def get_main_task_duration(self, rate=1) -> float:
        main_task_duration = random.uniform(2.5, 25.5)
        print("主任务耗时", main_task_duration)
        return main_task_duration
