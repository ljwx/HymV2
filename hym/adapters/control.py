from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from hym.core.config import ReportingSettings
from hym.core.control import DeviceControlState, RemoteCommand, TaskScope


ControlRequestSender = Callable[
    [str, str, Mapping[str, str], bytes | None, float],
    tuple[int, bytes],
]


class HttpRemoteControlClient:
    """运行控制使用短超时独立请求，服务端离线时不拖慢设备流程。"""

    def __init__(
        self,
        settings: ReportingSettings,
        *,
        sender: ControlRequestSender | None = None,
    ) -> None:
        self.settings = settings
        self._sender = sender or self._send_request
        self._base_url = settings.server_url.rstrip("/") + "/api/v1/automation/ingest"

    def control(self, device_id: str) -> DeviceControlState:
        payload = self._json_request("GET", f"/control/{_segment(device_id)}")
        return DeviceControlState(
            device_id=str(payload["deviceId"]),
            pause_requested=bool(payload["pauseRequested"]),
            requested_at_ms=_optional_int(payload.get("requestedAtMs")),
            pause_until_ms=_optional_int(payload.get("pauseUntilMs")),
            acknowledged_at_ms=_optional_int(payload.get("acknowledgedAtMs")),
            desired_state=str(payload.get("desiredState", "running")),
            state_requested_at_ms=_optional_int(payload.get("stateRequestedAtMs")),
            observed_state=str(payload.get("observedState", "offline")),
            observed_at_ms=_optional_int(payload.get("observedAtMs")),
        )

    def acknowledge_pause(self, device_id: str) -> None:
        self._json_request("POST", f"/control/{_segment(device_id)}/ack", {})

    def report_state(self, device_id: str, state: str) -> None:
        self._json_request("POST", f"/control/{_segment(device_id)}/state", {"state": state})

    def claim_command(self, device_id: str) -> RemoteCommand | None:
        status, payload = self._request("POST", f"/commands/{_segment(device_id)}/claim", {})
        if status == 204 or not payload:
            return None
        data = json.loads(payload)
        return RemoteCommand(
            command_id=str(data["id"]),
            device_id=str(data["deviceId"]),
            app_id=data.get("appId"),
            scope=TaskScope(str(data["scope"])),
            rounds=int(data["rounds"]),
            value=_optional_int(data.get("value")),
        )

    def complete_command(
        self,
        device_id: str,
        command_id: str,
        *,
        succeeded: bool,
        message: str,
    ) -> None:
        self._json_request(
            "POST",
            f"/commands/{_segment(device_id)}/{_segment(command_id)}/complete",
            {"status": "success" if succeeded else "failed", "message": message},
        )

    def _json_request(
        self,
        method: str,
        path: str,
        body: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        _, payload = self._request(method, path, body)
        return json.loads(payload) if payload else {}

    def _request(
        self,
        method: str,
        path: str,
        body: Mapping[str, object] | None = None,
    ) -> tuple[int, bytes]:
        encoded = None
        if body is not None:
            encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return self._sender(
            method,
            self._base_url + path,
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-JDCR-Automation-Key": self.settings.ingest_key,
            },
            encoded,
            self.settings.control_timeout_seconds,
        )

    @staticmethod
    def _send_request(
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout: float,
    ) -> tuple[int, bytes]:
        request = Request(url, data=body, headers=dict(headers), method=method)
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.status, response.read()
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"控制服务器返回 HTTP {error.code}: {detail[:300]}") from error
        except URLError as error:
            raise RuntimeError(f"无法连接运行控制服务器: {error.reason}") from error


def _segment(value: str) -> str:
    return quote(value, safe="")


def _optional_int(value: object) -> int | None:
    return int(value) if value is not None else None
