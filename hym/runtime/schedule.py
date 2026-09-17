from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping

from hym.core.ports import ClockPort, RandomPort, StateStorePort
from hym.core.randomness import bounded_normal


class DailyAppScheduler:
    """按应用配置生成当天执行时刻，并保证一天最多启动一次。"""

    def __init__(
        self,
        device_id: str,
        state: StateStorePort,
        clock: ClockPort,
        random_source: RandomPort,
    ) -> None:
        self.device_id = device_id
        self.state = state
        self.clock = clock
        self.random = random_source

    def is_due(self, app_id: str, options: Mapping[str, Any]) -> bool:
        if not bool(options.get("daily_once", False)):
            return True
        now = self.clock.now().astimezone()
        namespace = f"{self.device_id}:{app_id}"
        key = f"schedule:{now.date().isoformat()}"
        value = self.state.get(namespace, key, {})
        record = value if isinstance(value, dict) else {}
        if record.get("started_at"):
            return False
        due_at = record.get("due_at")
        if not isinstance(due_at, str):
            due_at = self._create_due_time(now, options).isoformat()
            self.state.set(namespace, key, {"due_at": due_at})
        if bool(options.get("daily_force_due", False)):
            return True
        return now >= datetime.fromisoformat(due_at)

    def mark_started(self, app_id: str, options: Mapping[str, Any]) -> None:
        if not bool(options.get("daily_once", False)):
            return
        now = self.clock.now().astimezone()
        namespace = f"{self.device_id}:{app_id}"
        key = f"schedule:{now.date().isoformat()}"
        value = self.state.get(namespace, key, {})
        record = dict(value) if isinstance(value, dict) else {}
        record["started_at"] = now.isoformat()
        self.state.set(namespace, key, record)

    def _create_due_time(self, now, options: Mapping[str, Any]):
        start = float(options.get("daily_window_start_hour", 9.0))
        center = float(options.get("daily_window_center_hour", 15.0))
        end = float(options.get("daily_window_end_hour", 22.0))
        stddev = float(options.get("daily_window_stddev_hours", max((end - start) / 6, 0.1)))
        if not 0 <= start <= center <= end < 24:
            raise ValueError("每日执行时间窗必须满足 0 <= start <= center <= end < 24")
        hour = bounded_normal(self.random, start, end, center=center, stddev=stddev)
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight + timedelta(hours=hour)
