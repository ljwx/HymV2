from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

from hym.core.models import DeviceDescriptor


@dataclass(frozen=True, slots=True)
class BehaviorSettings:
    """统一控制等待节奏，业务概率由各 App 单独配置。"""

    timing_scale: float = 1.0
    jitter_ratio: float = 0.12
    minimum_delay: float = 0.15
    operation_delay_min: float = 0.5
    operation_delay_center: float = 1.5
    operation_delay_max: float = 2.5
    operation_delay_stddev: float = 0.33
    touch_duration_min: float = 0.03
    touch_duration_center: float = 0.09
    touch_duration_max: float = 0.15
    touch_duration_stddev: float = 0.02
    touch_offset_ratio: float = 0.004
    swipe_duration_min: float = 0.18
    swipe_duration_center: float = 0.33
    swipe_duration_max: float = 0.48
    swipe_duration_stddev: float = 0.05
    swipe_x_min: float = 0.42
    swipe_x_max: float = 0.58
    swipe_up_start_min: float = 0.70
    swipe_up_start_max: float = 0.82
    swipe_up_end_min: float = 0.25
    swipe_up_end_max: float = 0.38
    reward_wait_scale: float = 1.0

    def __post_init__(self) -> None:
        if not 0.1 <= self.timing_scale <= 3.0:
            raise ValueError("等待倍率必须位于 0.1 到 3.0 之间")
        if not 0 <= self.jitter_ratio <= 0.5:
            raise ValueError("随机浮动比例必须位于 0 到 0.5 之间")
        if self.minimum_delay < 0:
            raise ValueError("最短等待时间不能小于零")
        if self.operation_delay_min > self.operation_delay_max:
            raise ValueError("操作等待范围无效")
        if not self.operation_delay_min <= self.operation_delay_center <= self.operation_delay_max:
            raise ValueError("操作等待中心值必须位于配置范围内")
        if self.operation_delay_stddev <= 0:
            raise ValueError("操作等待标准差必须大于零")
        if self.touch_duration_min > self.touch_duration_max:
            raise ValueError("触摸时长范围无效")
        if not self.touch_duration_min <= self.touch_duration_center <= self.touch_duration_max:
            raise ValueError("触摸时长中心值必须位于配置范围内")
        if self.touch_duration_stddev <= 0:
            raise ValueError("触摸时长标准差必须大于零")
        if not 0 <= self.touch_offset_ratio <= 0.05:
            raise ValueError("点击偏移比例必须位于 0 到 0.05 之间")
        if self.swipe_duration_min > self.swipe_duration_max:
            raise ValueError("滑动时长范围无效")
        if not self.swipe_duration_min <= self.swipe_duration_center <= self.swipe_duration_max:
            raise ValueError("滑动时长中心值必须位于配置范围内")
        if self.swipe_duration_stddev <= 0:
            raise ValueError("滑动时长标准差必须大于零")
        normalized_ranges = (
            (self.swipe_x_min, self.swipe_x_max),
            (self.swipe_up_start_min, self.swipe_up_start_max),
            (self.swipe_up_end_min, self.swipe_up_end_max),
        )
        if any(start < 0 or end > 1 or start > end for start, end in normalized_ranges):
            raise ValueError("滑动坐标范围无效")
        if not 0.5 <= self.reward_wait_scale <= 2.0:
            raise ValueError("奖励等待倍率必须位于 0.5 到 2.0 之间")

    def merged(self, values: Mapping[str, Any] | None) -> BehaviorSettings:
        if not values:
            return self
        allowed = {field_name for field_name in self.__dataclass_fields__}
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"未知行为配置: {', '.join(sorted(unknown))}")
        merged_values = dict(values)
        # 兼容只覆盖上下限的旧配置；显式中心值和标准差始终优先。
        for prefix in ("operation_delay", "touch_duration", "swipe_duration"):
            minimum_key = f"{prefix}_min"
            maximum_key = f"{prefix}_max"
            center_key = f"{prefix}_center"
            stddev_key = f"{prefix}_stddev"
            if not ({minimum_key, maximum_key} & merged_values.keys()):
                continue
            minimum = float(merged_values.get(minimum_key, getattr(self, minimum_key)))
            maximum = float(merged_values.get(maximum_key, getattr(self, maximum_key)))
            if center_key not in merged_values:
                merged_values[center_key] = (minimum + maximum) / 2
            if stddev_key not in merged_values:
                merged_values[stddev_key] = max((maximum - minimum) / 6, 0.001)
        return replace(self, **merged_values)


@dataclass(frozen=True, slots=True)
class RetrySettings:
    connect_attempts: int = 3
    reconnect_attempts: int = 2
    connect_backoff_seconds: float = 3.0
    observation_attempts: int = 2
    health_check_interval_seconds: float = 0.0

    def __post_init__(self) -> None:
        if min(self.connect_attempts, self.reconnect_attempts, self.observation_attempts) < 1:
            raise ValueError("重试次数必须大于零")
        if self.connect_backoff_seconds < 0:
            raise ValueError("重连等待时间不能小于零")
        if self.health_check_interval_seconds < 0:
            raise ValueError("健康检查间隔不能小于零")


@dataclass(frozen=True, slots=True)
class VisionSettings:
    enable_image_matching: bool = True
    enable_ocr: bool = False
    ocr_engine: str = "paddle"
    ocr_language: str = "ch"

    def __post_init__(self) -> None:
        if self.ocr_engine not in {"paddle", "macos_vision"}:
            raise ValueError("OCR 引擎必须是 paddle 或 macos_vision")


@dataclass(frozen=True, slots=True)
class LoggingSettings:
    console_level: str = "info"
    write_jsonl: bool = True
    jsonl_level: str = "info"

    def __post_init__(self) -> None:
        levels = {"debug", "info", "warning", "error"}
        if self.console_level not in levels:
            raise ValueError("控制台日志级别无效")
        if self.jsonl_level not in levels:
            raise ValueError("JSONL 日志级别无效")


@dataclass(frozen=True, slots=True)
class ReportingSettings:
    """运行数据批量上报；密钥默认从环境变量读取，避免写入仓库。"""

    enabled: bool = False
    server_url: str = ""
    ingest_key: str = ""
    level: str = "info"
    batch_size: int = 100
    timeout_seconds: float = 10.0
    retry_interval_seconds: float = 30.0
    upload_artifacts: bool = True

    def __post_init__(self) -> None:
        if self.enabled and not self.server_url.startswith(("http://", "https://")):
            raise ValueError("上报服务器地址必须以 http:// 或 https:// 开头")
        if self.enabled and not self.ingest_key:
            raise ValueError("启用运行数据上报时必须提供上报密钥")
        if self.level not in {"debug", "info", "warning", "error"}:
            raise ValueError("上报日志级别无效")
        if not 1 <= self.batch_size <= 500:
            raise ValueError("单批上报数量必须位于 1 到 500 之间")
        if self.timeout_seconds <= 0:
            raise ValueError("上报超时时间必须大于零")
        if self.retry_interval_seconds < 0:
            raise ValueError("上报重试间隔不能小于零")


@dataclass(frozen=True, slots=True)
class ProcessSettings:
    monitor_interval_seconds: float = 2.0
    restart_limit: int = 3

    def __post_init__(self) -> None:
        if self.monitor_interval_seconds <= 0:
            raise ValueError("进程检查间隔必须大于零")
        if self.restart_limit < 0:
            raise ValueError("工作进程重启上限不能小于零")


@dataclass(frozen=True, slots=True)
class DiagnosticsSettings:
    consecutive_failure_threshold: int = 3
    capture_every_failures: int = 3

    def __post_init__(self) -> None:
        if self.consecutive_failure_threshold < 2:
            raise ValueError("诊断采集阈值至少为 2 次")
        if self.capture_every_failures < 1:
            raise ValueError("重复诊断采集间隔必须大于零")


@dataclass(frozen=True, slots=True)
class InterruptionSettings:
    """只在安全点触发 App 切换或桌面停留。"""

    enabled: bool = False
    checkpoint_probability: float = 0.08
    desktop_pause_probability: float = 0.3
    desktop_wait_seconds_min: float = 20.0
    desktop_wait_seconds_center: float = 40.0
    desktop_wait_seconds_max: float = 60.0
    desktop_wait_seconds_stddev: float = 7.0
    min_interval_seconds: float = 120.0
    max_per_cycle: int = 2

    def __post_init__(self) -> None:
        probabilities = (self.checkpoint_probability, self.desktop_pause_probability)
        if any(value < 0 or value > 1 for value in probabilities):
            raise ValueError("插空概率必须位于 0 到 1 之间")
        if self.desktop_wait_seconds_min < 0:
            raise ValueError("桌面等待时间不能小于零")
        if self.desktop_wait_seconds_min > self.desktop_wait_seconds_max:
            raise ValueError("桌面等待时间范围无效")
        if not (
            self.desktop_wait_seconds_min
            <= self.desktop_wait_seconds_center
            <= self.desktop_wait_seconds_max
        ):
            raise ValueError("桌面等待中心值必须位于配置范围内")
        if self.desktop_wait_seconds_stddev <= 0:
            raise ValueError("桌面等待标准差必须大于零")
        if self.min_interval_seconds < 0:
            raise ValueError("插空最短间隔不能小于零")
        if self.max_per_cycle < 0:
            raise ValueError("单轮插空次数不能小于零")


@dataclass(frozen=True, slots=True)
class AppRunSettings:
    app_id: str
    enabled: bool = True
    behavior: Mapping[str, Any] = field(default_factory=dict)
    options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DeviceRunSettings:
    descriptor: DeviceDescriptor
    apps: tuple[AppRunSettings, ...]
    behavior: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    behavior: BehaviorSettings
    retry: RetrySettings
    vision: VisionSettings
    logging: LoggingSettings
    reporting: ReportingSettings
    processes: ProcessSettings
    diagnostics: DiagnosticsSettings
    devices: tuple[DeviceRunSettings, ...]
    interruptions: InterruptionSettings = field(default_factory=InterruptionSettings)
    log_dir: Path = Path("runtime/logs")
    state_dir: Path = Path("runtime/state")
    artifact_dir: Path = Path("runtime/artifacts")
    resource_dir: Path = Path("resource")
    report_queue_dir: Path = Path("runtime/report_queue")
    loop_interval_seconds: float = 10.0

    def behavior_for(self, device: DeviceRunSettings, app: AppRunSettings) -> BehaviorSettings:
        return self.behavior.merged(device.behavior).merged(app.behavior)


def load_runtime_settings(path: str | Path) -> RuntimeSettings:
    """加载版本简单、容易手工修改的 JSON 配置。"""

    config_path = Path(path)
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    base_dir = config_path.parent.parent if config_path.parent.name == "config" else config_path.parent

    behavior = BehaviorSettings().merged(raw.get("behavior", {}))
    retry = RetrySettings(**raw.get("retry", {}))
    vision = VisionSettings(**raw.get("vision", {}))
    logging = LoggingSettings(**raw.get("logging", {}))
    reporting_values = dict(raw.get("reporting", {}))
    ingest_key_env = str(reporting_values.pop("ingest_key_env", "JDCR_AUTOMATION_INGEST_KEY"))
    if not reporting_values.get("ingest_key"):
        reporting_values["ingest_key"] = os.environ.get(ingest_key_env, "")
    reporting = ReportingSettings(**reporting_values)
    processes = ProcessSettings(**raw.get("processes", {}))
    diagnostics = DiagnosticsSettings(**raw.get("diagnostics", {}))
    interruption_values = dict(raw.get("interruptions", {}))
    _fill_range_defaults(
        interruption_values,
        minimum_key="desktop_wait_seconds_min",
        center_key="desktop_wait_seconds_center",
        maximum_key="desktop_wait_seconds_max",
        stddev_key="desktop_wait_seconds_stddev",
        default_minimum=20.0,
        default_maximum=60.0,
    )
    interruptions = InterruptionSettings(**interruption_values)
    devices = tuple(_parse_device(item) for item in raw.get("devices", ()))
    if not devices:
        raise ValueError("至少需要配置一台设备")
    _validate_devices(devices)

    paths = raw.get("paths", {})
    runtime = raw.get("runtime", {})
    loop_interval = float(runtime.get("loop_interval_seconds", 10.0))
    if loop_interval < 0:
        raise ValueError("轮次间隔不能小于零")
    return RuntimeSettings(
        behavior=behavior,
        retry=retry,
        vision=vision,
        logging=logging,
        reporting=reporting,
        processes=processes,
        diagnostics=diagnostics,
        devices=devices,
        interruptions=interruptions,
        log_dir=_resolve_path(base_dir, paths.get("logs", "runtime/logs")),
        state_dir=_resolve_path(base_dir, paths.get("state", "runtime/state")),
        artifact_dir=_resolve_path(base_dir, paths.get("artifacts", "runtime/artifacts")),
        resource_dir=_resolve_path(base_dir, paths.get("resources", "resource")),
        report_queue_dir=_resolve_path(base_dir, paths.get("report_queue", "runtime/report_queue")),
        loop_interval_seconds=loop_interval,
    )


def _parse_device(raw: Mapping[str, Any]) -> DeviceRunSettings:
    device_id = str(raw["device_id"])
    descriptor = DeviceDescriptor(
        device_id=device_id,
        platform=str(raw.get("platform", "android")),
        connection=str(raw.get("connection") or device_id),
        model=raw.get("model"),
        metadata=raw.get("metadata", {}),
    )
    apps = tuple(
        AppRunSettings(
            app_id=str(item["app_id"]),
            enabled=bool(item.get("enabled", True)),
            behavior=item.get("behavior", {}),
            options=item.get("options", {}),
        )
        for item in raw.get("apps", ())
    )
    return DeviceRunSettings(descriptor=descriptor, apps=apps, behavior=raw.get("behavior", {}))


def _resolve_path(base_dir: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base_dir / path).resolve()


def _validate_devices(devices: tuple[DeviceRunSettings, ...]) -> None:
    device_ids = [device.descriptor.device_id for device in devices]
    if len(device_ids) != len(set(device_ids)):
        raise ValueError("设备 ID 不能重复")
    for device in devices:
        app_ids = [app.app_id for app in device.apps]
        if len(app_ids) != len(set(app_ids)):
            raise ValueError(f"设备 {device.descriptor.device_id} 的应用 ID 不能重复")
        for app in device.apps:
            _validate_app_options(app)


def _validate_app_options(app: AppRunSettings) -> None:
    for key, value in app.options.items():
        if key.endswith("_probability"):
            probability = float(value)
            if not 0 <= probability <= 1:
                raise ValueError(f"应用 {app.app_id} 的概率配置 {key} 必须位于 0 到 1 之间")
        if key.endswith("_min"):
            maximum_key = key[:-4] + "_max"
            if maximum_key in app.options and float(value) > float(app.options[maximum_key]):
                raise ValueError(f"应用 {app.app_id} 的范围配置 {key}/{maximum_key} 无效")
        if key.endswith("_swipes") and int(value) < 0:
            raise ValueError(f"应用 {app.app_id} 的滑动次数配置 {key} 不能小于零")
        if key.endswith("_center"):
            prefix = key[:-7]
            minimum_key = prefix + "_min"
            maximum_key = prefix + "_max"
            if minimum_key in app.options and maximum_key in app.options:
                if not float(app.options[minimum_key]) <= float(value) <= float(
                    app.options[maximum_key]
                ):
                    raise ValueError(f"应用 {app.app_id} 的中心值配置 {key} 超出范围")
        if key.endswith("_stddev") and float(value) <= 0:
            raise ValueError(f"应用 {app.app_id} 的标准差配置 {key} 必须大于零")
        if key.endswith("_post_classification_min_seconds") and float(value) < 0:
            raise ValueError(f"应用 {app.app_id} 的分类后最短停留 {key} 不能小于零")
    quick_probability = float(app.options.get("uninterested_video_probability", 0.08))
    full_probability = float(app.options.get("full_watch_attempt_probability", 0.25))
    if quick_probability + full_probability > 1:
        raise ValueError(f"应用 {app.app_id} 的快速划过和完整观看尝试概率之和不能超过 1")


def _fill_range_defaults(
    values: dict[str, Any],
    *,
    minimum_key: str,
    center_key: str,
    maximum_key: str,
    stddev_key: str,
    default_minimum: float,
    default_maximum: float,
) -> None:
    if minimum_key not in values and maximum_key not in values:
        return
    minimum = float(values.get(minimum_key, default_minimum))
    maximum = float(values.get(maximum_key, default_maximum))
    values.setdefault(center_key, (minimum + maximum) / 2)
    values.setdefault(stddev_key, max((maximum - minimum) / 6, 0.001))
