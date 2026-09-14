from __future__ import annotations

from dataclasses import dataclass

from hym.core.config import BehaviorSettings
from hym.core.ports import ClockPort, RandomPort
from hym.core.randomness import bounded_normal


@dataclass(slots=True)
class BehaviorTiming:
    settings: BehaviorSettings
    clock: ClockPort
    random: RandomPort

    def baseline_seconds(self, base_seconds: float, *, reward_wait: bool = False) -> float:
        """返回不带随机浮动的基准时间，适合超时兜底。"""

        scale = self.settings.reward_wait_scale if reward_wait else self.settings.timing_scale
        return max(self.settings.minimum_delay, base_seconds * scale)

    def scaled_seconds(self, base_seconds: float, *, reward_wait: bool = False) -> float:
        center = self.baseline_seconds(base_seconds, reward_wait=reward_wait)
        spread = center * self.settings.jitter_ratio
        # 奖励倒计时不能向下浮动，否则可能在奖励到账前提前退出。
        lower = center if reward_wait else max(0.0, center - spread)
        sampled = bounded_normal(self.random, lower, center + spread, center=center)
        return max(self.settings.minimum_delay, sampled)

    def range_seconds(
        self,
        minimum: float,
        maximum: float,
        *,
        center: float | None = None,
        stddev: float | None = None,
        reward_wait: bool = False,
    ) -> float:
        scale = self.settings.reward_wait_scale if reward_wait else self.settings.timing_scale
        scaled_minimum = max(self.settings.minimum_delay, minimum * scale)
        scaled_maximum = max(scaled_minimum, maximum * scale)
        scaled_center = None if center is None else max(scaled_minimum, min(scaled_maximum, center * scale))
        scaled_stddev = None if stddev is None else stddev * scale
        # 已配置范围本身就是随机模型，不再叠加 jitter，保证采样不会越过上下限。
        return bounded_normal(
            self.random,
            scaled_minimum,
            scaled_maximum,
            center=scaled_center,
            stddev=scaled_stddev,
        )

    def operation_delay(self, times: int = 1) -> None:
        for _ in range(times):
            self.clock.sleep(
                self.range_seconds(
                    self.settings.operation_delay_min,
                    self.settings.operation_delay_max,
                    center=self.settings.operation_delay_center,
                    stddev=self.settings.operation_delay_stddev,
                )
            )

    def wait(self, base_seconds: float, *, reward_wait: bool = False) -> float:
        duration = self.scaled_seconds(base_seconds, reward_wait=reward_wait)
        self.clock.sleep(duration)
        return duration

    def touch_duration(self) -> float:
        return bounded_normal(
            self.random,
            self.settings.touch_duration_min,
            self.settings.touch_duration_max,
            center=self.settings.touch_duration_center,
            stddev=self.settings.touch_duration_stddev,
        )

    def swipe_duration(self) -> float:
        return bounded_normal(
            self.random,
            self.settings.swipe_duration_min,
            self.settings.swipe_duration_max,
            center=self.settings.swipe_duration_center,
            stddev=self.settings.swipe_duration_stddev,
        )
