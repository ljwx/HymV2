from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from hym.core.models import ArtifactRef, utc_now


class EventLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class AutomationEvent:
    event_type: str
    trace_id: str
    device_id: str
    event_id: str = field(default_factory=lambda: uuid4().hex)
    occurred_at: datetime = field(default_factory=utc_now)
    schema_version: str = "1.0"
    level: EventLevel = EventLevel.INFO
    event_name: str = ""
    message: str = ""
    cycle_id: str | None = None
    app_run_id: str | None = None
    step_run_id: str | None = None
    app_id: str | None = None
    workflow_id: str | None = None
    step_id: str | None = None
    status: str | None = None
    data: Mapping[str, Any] = field(default_factory=dict)
    artifacts: tuple[ArtifactRef, ...] = ()


def to_jsonable(value: Any) -> Any:
    """把领域对象转换成稳定的 JSON 数据。"""

    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, bytes):
        raise TypeError("事件中不能直接写入二进制数据，请先保存为产物")
    return value


class InMemoryEventSink:
    def __init__(self) -> None:
        self.events: list[AutomationEvent] = []
        self._lock = threading.Lock()

    def emit(self, event: AutomationEvent) -> None:
        with self._lock:
            self.events.append(event)


_LEVEL_ORDER = {
    EventLevel.DEBUG: 10,
    EventLevel.INFO: 20,
    EventLevel.WARNING: 30,
    EventLevel.ERROR: 40,
}


@dataclass(frozen=True, slots=True)
class EventFilter:
    min_level: EventLevel = EventLevel.INFO
    event_prefixes: tuple[str, ...] = ()
    device_ids: tuple[str, ...] = ()
    app_ids: tuple[str, ...] = ()

    def accepts(self, event: AutomationEvent) -> bool:
        if _LEVEL_ORDER[event.level] < _LEVEL_ORDER[self.min_level]:
            return False
        if self.event_prefixes and not event.event_type.startswith(self.event_prefixes):
            return False
        if self.device_ids and event.device_id not in self.device_ids:
            return False
        if self.app_ids and event.app_id not in self.app_ids:
            return False
        return True
