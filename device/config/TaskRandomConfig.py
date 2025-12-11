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
        main_task_duration = random.uniform(3.5, 25.5)
        print("主任务耗时", main_task_duration)
        return main_task_duration

    def get_main_task_duration_with_movie(self) -> float:
        movie_duration = random.uniform(5.5, 120.5)
        print("主任务电影耗时", movie_duration)
        return movie_duration

    def get_main_task_duration_with_ad(self) -> float:
        ad_duration = random.uniform(0.5, 5.5)
        print("主任务广告耗时", ad_duration)
        return ad_duration

    def get_video_ad_duration(self, time: float) -> float:
        diff = time * 0.15
        return random.uniform(time - diff, time + diff)
