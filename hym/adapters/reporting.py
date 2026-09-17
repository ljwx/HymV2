from __future__ import annotations

import json
import os
import sys
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from hym.core.config import ReportingSettings
from hym.core.events import AutomationEvent, EventFilter, to_jsonable
from hym.core.models import AppIdentity, DeviceDescriptor


RequestSender = Callable[[str, str, Mapping[str, str], bytes], bytes]


class DurableHttpEventSink:
    """先持久化再批量上报，网络异常不会阻断设备任务。"""

    def __init__(
        self,
        settings: ReportingSettings,
        queue_path: str | Path,
        device: DeviceDescriptor,
        apps: Iterable[AppIdentity],
        *,
        event_filter: EventFilter | None = None,
        sender: RequestSender | None = None,
    ) -> None:
        self.settings = settings
        self.queue_path = Path(queue_path)
        self.device = device
        self.apps = tuple(apps)
        self._filter = event_filter
        self._sender = sender or self._send_request
        self._lock = threading.Lock()
        self._last_error = ""
        self._pending_count = self._line_count()
        self._next_retry_at = 0.0

    def emit(self, event: AutomationEvent) -> None:
        if self._filter is not None and not self._filter.accepts(event):
            return
        # 连接阶段尚未建立任务轮次，只保留在本地日志，不进入运行中心。
        if not event.cycle_id:
            return
        payload = json.dumps(to_jsonable(event), ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self.queue_path.parent.mkdir(parents=True, exist_ok=True)
            with self.queue_path.open("a", encoding="utf-8") as file:
                file.write(payload)
                file.write("\n")
                file.flush()
            self._pending_count += 1
            flush_all = event.event_type == "runtime.cycle.finished"
            should_flush = flush_all or self._pending_count >= self.settings.batch_size
            if should_flush and time.monotonic() >= self._next_retry_at:
                try:
                    self._flush(flush_all=flush_all)
                    self._last_error = ""
                    self._next_retry_at = 0.0
                except Exception as error:
                    self._next_retry_at = time.monotonic() + self.settings.retry_interval_seconds
                    message = str(error)
                    if message != self._last_error:
                        print(f"运行数据上报暂时失败，已保留本地队列: {message}", file=sys.stderr)
                        self._last_error = message

    def flush(self) -> None:
        """供测试和退出钩子显式触发；失败时保留原队列。"""

        with self._lock:
            self._flush(flush_all=True)

    def _flush(self, *, flush_all: bool) -> None:
        while True:
            lines = self._read_lines()
            if not lines:
                return
            if not flush_all and len(lines) < self.settings.batch_size:
                return
            batch_lines = lines[: self.settings.batch_size]
            events = [event for line in batch_lines if (event := json.loads(line)).get("cycle_id")]
            if events:
                self._upload_events(events)
                if self.settings.upload_artifacts:
                    self._upload_artifacts(events)
            self._rewrite_lines(lines[len(batch_lines) :])
            if not flush_all:
                return

    def _upload_events(self, events: list[dict[str, Any]]) -> None:
        request = {
            "schema_version": "1.0",
            "source": "hym",
            "device": {
                "device_id": self.device.device_id,
                "platform": self.device.platform,
                "model": self.device.model,
                "metadata": to_jsonable(self.device.metadata),
            },
            "apps": [
                {
                    "app_id": app.app_id,
                    "display_name": app.display_name,
                    "package_name": app.package_name,
                }
                for app in self.apps
            ],
            "events": events,
        }
        self._sender(
            "POST",
            f"{self.settings.server_url.rstrip('/')}/api/v1/automation/ingest/events",
            self._headers("application/json"),
            json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        )

    def _upload_artifacts(self, events: list[dict[str, Any]]) -> None:
        for event in events:
            for artifact in event.get("artifacts", ()):
                path = Path(str(artifact.get("uri", "")))
                if not path.is_file():
                    continue
                headers = self._headers(str(artifact.get("media_type") or "application/octet-stream"))
                sha256 = artifact.get("sha256")
                if sha256:
                    headers["X-Content-SHA256"] = str(sha256)
                self._sender(
                    "PUT",
                    f"{self.settings.server_url.rstrip('/')}/api/v1/automation/ingest/artifacts/{artifact['artifact_id']}",
                    headers,
                    path.read_bytes(),
                )

    def _headers(self, content_type: str) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": content_type,
            "X-JDCR-Automation-Key": self.settings.ingest_key,
        }

    def _send_request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> bytes:
        request = Request(url, data=body, headers=dict(headers), method=method)
        try:
            with urlopen(request, timeout=self.settings.timeout_seconds) as response:
                return response.read()
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"服务器返回 HTTP {error.code}: {detail[:300]}") from error
        except URLError as error:
            raise RuntimeError(f"无法连接运行数据服务器: {error.reason}") from error

    def _read_lines(self) -> list[str]:
        if not self.queue_path.exists():
            return []
        return [line for line in self.queue_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _line_count(self) -> int:
        return len(self._read_lines())

    def _rewrite_lines(self, lines: list[str]) -> None:
        if not lines:
            self.queue_path.unlink(missing_ok=True)
            self._pending_count = 0
            return
        temporary = self.queue_path.with_suffix(self.queue_path.suffix + ".tmp")
        temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(temporary, self.queue_path)
        self._pending_count = len(lines)
