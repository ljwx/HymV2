from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from hym.core.config import InterruptionSettings
from hym.core.ports import ClockPort, RandomPort


class InterruptionKind(str, Enum):
    APP_SWITCH = "app_switch"
    DESKTOP_PAUSE = "desktop_pause"


@dataclass(frozen=True, slots=True)
class InterruptionRequest:
    kind: InterruptionKind
    checkpoint: str
    data: Mapping[str, Any] = field(default_factory=dict)


class WorkflowYield(Exception):
    """在安全点暂停当前步骤，不把暂停当作失败。"""

    def __init__(self, request: InterruptionRequest) -> None:
        super().__init__(request.checkpoint)
        self.request = request


@dataclass(slots=True)
class InterruptionPolicy:
    settings: InterruptionSettings
    clock: ClockPort
    random: RandomPort
    interruption_count: int = 0
    _last_interruption_at: datetime | None = None

    def request(
        self,
        checkpoint: str,
        data: Mapping[str, Any] | None = None,
    ) -> InterruptionRequest | None:
        if not self.settings.enabled:
            return None
        if self.interruption_count >= self.settings.max_per_cycle:
            return None
        now = self.clock.now()
        if self._last_interruption_at is not None:
            elapsed = (now - self._last_interruption_at).total_seconds()
            if elapsed < self.settings.min_interval_seconds:
                return None
        if self.random.random() >= self.settings.checkpoint_probability:
            return None
        kind = (
            InterruptionKind.DESKTOP_PAUSE
            if self.random.random() < self.settings.desktop_pause_probability
            else InterruptionKind.APP_SWITCH
        )
        self.interruption_count += 1
        self._last_interruption_at = now
        return InterruptionRequest(kind, checkpoint, data or {})

    def yield_if_requested(
        self,
        checkpoint: str,
        data: Mapping[str, Any] | None = None,
    ) -> None:
        request = self.request(checkpoint, data)
        if request is not None:
            raise WorkflowYield(request)
