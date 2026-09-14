from __future__ import annotations

import argparse
from pathlib import Path

from wechat_automation.config import load_wechat_settings
from wechat_automation.runner import run_wechat


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="微信基本操作运行器")
    parser.add_argument("--config", default="config/wechat.local.json", help="微信独立配置文件")
    parser.add_argument("--device", help="覆盖配置中的设备 ID")
    parser.add_argument("--loop", action="store_true", help="按公共配置间隔持续运行")
    parser.add_argument("--check-config", action="store_true", help="只校验配置，不连接手机")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = Path(args.config).resolve()
    settings = load_wechat_settings(config_path)
    # 公共配置也在检查阶段加载，避免运行到连接设备时才发现错误。
    if args.check_config:
        from hym.core.config import load_runtime_settings

        runtime = load_runtime_settings(settings.runtime_config)
        runtime.behavior.merged(settings.behavior)
        print(f"微信配置校验成功: {config_path}")
        return 0
    return run_wechat(settings, loop=args.loop, device_id=args.device)
