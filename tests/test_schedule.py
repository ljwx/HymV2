import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from hym.runtime.schedule import DailyAppScheduler
from hym.testing import DeterministicRandom, FakeClock, InMemoryStateStore


class DailyAppSchedulerTest(unittest.TestCase):
    def test_waits_until_sampled_time_and_runs_only_once(self):
        clock = FakeClock(datetime(2026, 9, 17, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai")))
        scheduler = DailyAppScheduler(
            "device-1",
            InMemoryStateStore(),
            clock,
            DeterministicRandom(),
        )
        options = {
            "daily_once": True,
            "daily_window_start_hour": 9,
            "daily_window_center_hour": 15,
            "daily_window_end_hour": 22,
            "daily_window_stddev_hours": 2,
        }

        self.assertFalse(scheduler.is_due("wechat", options))
        clock.sleep(7 * 60 * 60)
        self.assertTrue(scheduler.is_due("wechat", options))
        scheduler.mark_started("wechat", options)
        self.assertFalse(scheduler.is_due("wechat", options))


if __name__ == "__main__":
    unittest.main()
