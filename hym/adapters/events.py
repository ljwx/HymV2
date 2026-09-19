from __future__ import annotations

import json
import sys
import threading
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from hym.core.events import AutomationEvent, EventFilter, EventLevel, to_jsonable


class JsonlEventSink:
    """把领域事件追加到本地队列，供上报器增量消费。"""

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
