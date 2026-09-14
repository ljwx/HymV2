from __future__ import annotations

from dataclasses import replace

from hym.apps.registry import AppRegistry
from hym.core.config import AppRunSettings, DeviceRunSettings, load_runtime_settings
from hym.runtime.runner import DeviceWorker
from wechat_automation.config import WechatSettings
from wechat_automation.plugin import WechatPlugin


def run_wechat(settings: WechatSettings, *, loop: bool = False, device_id: str | None = None) -> int:
    runtime = load_runtime_settings(settings.runtime_config)
    runtime = replace(
        runtime,
        vision=replace(
            runtime.vision,
            enable_ocr=True,
            ocr_engine=settings.ocr_engine,
            ocr_language=settings.ocr_language,
        ),
    )
    selected_id = device_id or settings.device_id
    device = _select_device(runtime.devices, selected_id)
    app_settings = AppRunSettings(
        app_id="wechat",
        behavior=settings.behavior,
        options={
            "launch_wait_seconds": settings.launch_wait_seconds,
            "stop_app_probability": settings.stop_app_probability,
            "allow_interruptions": False,
        },
    )
    wechat_device = replace(device, apps=(app_settings,))
    registry = AppRegistry()
    registry.register(WechatPlugin(settings))
    return DeviceWorker(runtime, wechat_device, registry).run(once=not loop)


def _select_device(
    devices: tuple[DeviceRunSettings, ...],
    device_id: str | None,
) -> DeviceRunSettings:
    if device_id is None:
        return devices[0]
    device = next((item for item in devices if item.descriptor.device_id == device_id), None)
    if device is None:
        raise ValueError(f"公共运行配置中没有设备: {device_id}")
    return device
