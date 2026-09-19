from __future__ import annotations

from dataclasses import replace

from hym.adapters.events import CompositeEventSink, ConsoleEventSink, JsonlEventSink
from hym.adapters.reporting import DurableHttpEventSink
from hym.apps.registry import AppRegistry
from hym.apps.specs import AppSpec
from hym.core.config import DeviceRunSettings, RuntimeSettings
from hym.core.events import EventFilter, EventLevel
from hym.core.models import AppIdentity


def create_worker_event_sink(
    settings: RuntimeSettings,
    device: DeviceRunSettings,
    registry: AppRegistry,
):
    device_id = safe_id(device.descriptor.device_id)
    sinks = [
        ConsoleEventSink(EventFilter(min_level=EventLevel(settings.logging.console_level))),
    ]
    if settings.logging.write_jsonl:
        sinks.append(
            JsonlEventSink(
                settings.log_dir / f"{device_id}.jsonl",
                EventFilter(min_level=EventLevel(settings.logging.jsonl_level)),
            )
        )
    if settings.reporting.enabled:
        enabled_app_ids = {app.app_id for app in device.apps if app.enabled}
        apps = tuple(
            _reporting_identity(plugin.spec)
            for app_id in registry.app_ids()
            if app_id in enabled_app_ids and (plugin := registry.get(app_id)) is not None
        )
        sinks.append(
            DurableHttpEventSink(
                settings.reporting,
                settings.report_queue_dir / f"{device_id}.jsonl",
                device.descriptor,
                apps,
                event_filter=EventFilter(min_level=EventLevel(settings.reporting.level)),
            )
        )
    return CompositeEventSink(sinks)


def safe_id(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_." else "_" for char in value)


def _reporting_identity(spec: AppSpec) -> AppIdentity:
    """从业务规格生成上报能力，新 App 无需重复维护。"""

    inferred = tuple(
        name
        for name, field_name in (
            ("check_in", "check_in"),
            ("balance", "balance"),
            ("withdrawal", "withdrawal"),
            ("duration_reward", "duration_reward"),
            ("ad_reward", "ad"),
            ("content", "content"),
        )
        if getattr(spec, field_name, None) is not None
    )
    identity = spec.identity
    capabilities = tuple(dict.fromkeys((*identity.metadata.get("capabilities", ()), *inferred)))
    return replace(identity, metadata={**identity.metadata, "capabilities": capabilities})
