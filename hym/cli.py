from __future__ import annotations

import argparse
from pathlib import Path

from hym.apps.registry import create_configured_registry
from hym.core.config import load_runtime_settings
from hym.runtime.recorder import run_manual_flow_recording
from hym.runtime.runner import run_device_from_config
from hym.runtime.supervisor import run_supervised


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hym Android 自动任务运行器")
    parser.add_argument("--config", default="config/automation.json", help="运行配置文件")
    parser.add_argument("--device", action="append", default=[], help="只运行指定设备，可重复传入")
    parser.add_argument("--app", action="append", default=[], help="只运行指定 App，可重复传入")
    parser.add_argument("--once", action="store_true", help="每个 App 只执行一轮")
    parser.add_argument("--direct", action="store_true", help="不启用设备进程隔离，仅用于本地调试")
    parser.add_argument("--check-config", action="store_true", help="只校验配置，不连接设备")
    parser.add_argument("--list-apps", action="store_true", help="列出已注册的 App 插件")
    parser.add_argument("--record-flow", metavar="名称", help="交互式记录一次真机新流程")
    parser.add_argument("--record-app", metavar="APP", help="流程所属 App 名称或 app_id，仅作记录")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = Path(args.config).resolve()
    settings = load_runtime_settings(config_path)
    if args.check_config:
        print(f"配置校验成功: {config_path}")
        return 0
    if args.list_apps:
        configured_apps = (
            app.app_id
            for device in settings.devices
            for app in device.apps
            if app.enabled
        )
        registry = create_configured_registry(config_path, configured_apps)
        print("已注册应用: " + "、".join(registry.app_ids()))
        return 0
    if args.record_flow:
        selected = args.device or [settings.devices[0].descriptor.device_id]
        if len(selected) != 1:
            raise ValueError("手动流程记录一次只能选择一台设备")
        return run_manual_flow_recording(
            settings,
            device_id=selected[0],
            flow_name=args.record_flow,
            app_label=args.record_app,
        )
    if args.direct:
        selected = args.device or [settings.devices[0].descriptor.device_id]
        if len(selected) != 1:
            raise ValueError("直接运行模式一次只能指定一台设备")
        return run_device_from_config(config_path, selected[0], args.once, app_ids=args.app)
    return run_supervised(
        config_path,
        once=args.once,
        device_ids=args.device,
        app_ids=args.app,
    )
