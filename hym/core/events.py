from __future__ import annotations

import json
import sys
import threading
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping
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


class JsonlEventSink:
    """本地事件队列，后续可由上报器增量消费。"""

    def __init__(self, path: str | Path, event_filter: EventFilter | None = None) -> None:
        self.path = Path(path)
        self._filter = event_filter
        self._lock = threading.Lock()

    def emit(self, event: AutomationEvent) -> None:
        if self._filter is not None and not self._filter.accepts(event):
            return
        payload = json.dumps(to_jsonable(event), ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as file:
                file.write(payload)
                file.write("\n")
                file.flush()


_LEVEL_ORDER = {
    EventLevel.DEBUG: 10,
    EventLevel.INFO: 20,
    EventLevel.WARNING: 30,
    EventLevel.ERROR: 40,
}

_LEVEL_TEXT = {
    EventLevel.DEBUG: "调试",
    EventLevel.INFO: "信息",
    EventLevel.WARNING: "警告",
    EventLevel.ERROR: "错误",
}

_STATUS_TEXT = {
    "success": "成功",
    "already_done": "已完成",
    "skipped": "已跳过",
    "partial": "部分完成",
    "retryable_failure": "可重试失败",
    "no_progress": "无进展",
    "fatal": "严重失败",
    "failed": "失败",
    "timeout": "超时",
    "unavailable": "不可用",
    "cancelled": "已取消",
    "started": "已开始",
    "running": "执行中",
    "suspended": "已暂停",
    "waiting": "等待中",
    "recovering": "恢复中",
    "pending_confirmation": "已执行待确认",
    "confirmed": "已确认",
    "uncertain": "结果不确定",
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


class ConsoleEventSink:
    """输出紧凑中文日志，详细数据可按级别保留在 JSONL。"""

    def __init__(self, event_filter: EventFilter | None = None, stream=None) -> None:
        self._filter = event_filter or EventFilter()
        self._stream = stream or sys.stdout
        self._lock = threading.Lock()

    def emit(self, event: AutomationEvent) -> None:
        if not self._filter.accepts(event):
            return

        chain_parts = tuple(
            value[:8]
            for value in (event.cycle_id, event.app_run_id, event.step_run_id)
            if value
        )
        chain = "/".join(chain_parts) if chain_parts else event.trace_id[:8]
        fields = [
            event.occurred_at.astimezone().strftime("%Y-%m-%d %H:%M:%S"),
            f"级别={_LEVEL_TEXT[event.level]}",
            f"事件={event.event_name or '未命名事件'}",
            f"事件码={event.event_type}",
            f"链路={chain}",
            f"设备={event.device_id}",
        ]
        optional_fields = (
            ("应用", event.app_id),
            ("工作流", event.workflow_id),
            ("步骤", event.step_id),
            ("结果", _STATUS_TEXT.get(event.status, event.status) if event.status else None),
        )
        fields.extend(f"{name}={value}" for name, value in optional_fields if value)
        if event.message:
            fields.append(f"消息={json.dumps(event.message, ensure_ascii=False)}")

        with self._lock:
            print(" ".join(fields), file=self._stream, flush=True)


class CompositeEventSink:
    def __init__(self, sinks: Iterable[Any], *, strict: bool = False) -> None:
        self._sinks = tuple(sinks)
        self._strict = strict
        self.errors: list[str] = []

    def emit(self, event: AutomationEvent) -> None:
        for sink in self._sinks:
            try:
                sink.emit(event)
            except Exception as error:
                self.errors.append(f"{type(sink).__name__}: {error}")
                if self._strict:
                    raise
