from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TaskScope(str, Enum):
    """远程可选的业务范围，并保留工作流内部的准备与收尾分类。"""

    FULL = "full"
    CHECK_IN = "check_in"
    BALANCE = "balance"
    AD_REWARD = "ad_reward"
    MAIN = "main"
    SETUP = "setup"
    CLEANUP = "cleanup"
    FULL_ONLY = "full_only"

    @property
    def display_name(self) -> str:
        return {
            TaskScope.FULL: "完整任务",
            TaskScope.CHECK_IN: "签到任务",
            TaskScope.BALANCE: "余额任务",
            TaskScope.AD_REWARD: "广告奖励任务",
            TaskScope.MAIN: "主线任务",
            TaskScope.SETUP: "准备步骤",
            TaskScope.CLEANUP: "收尾步骤",
            TaskScope.FULL_ONLY: "完整流程专用步骤",
        }[self]


@dataclass(frozen=True, slots=True)
class DeviceControlState:
    device_id: str
    pause_requested: bool
    requested_at_ms: int | None = None
    pause_until_ms: int | None = None
    acknowledged_at_ms: int | None = None


@dataclass(frozen=True, slots=True)
class RemoteCommand:
    command_id: str
    device_id: str
    app_id: str | None
    scope: TaskScope
    rounds: int
