from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class MomentsSettings:
    enabled: bool = True
    swipes_min: int = 2
    swipes_center: float = 3.5
    swipes_max: int = 5
    swipes_stddev: float = 0.5
    pause_min_seconds: float = 2.5
    pause_center_seconds: float = 4.0
    pause_max_seconds: float = 6.0
    pause_stddev_seconds: float = 0.58

    def __post_init__(self) -> None:
        if self.swipes_min < 0 or self.swipes_min > self.swipes_max:
            raise ValueError("朋友圈滑动次数范围无效")
        if self.swipes_max > 30:
            raise ValueError("朋友圈单轮滑动次数不能超过 30")
        if not self.swipes_min <= self.swipes_center <= self.swipes_max:
            raise ValueError("朋友圈滑动次数中心值超出范围")
        if self.swipes_stddev <= 0:
            raise ValueError("朋友圈滑动次数标准差必须大于零")
        if self.pause_min_seconds < 0 or self.pause_min_seconds > self.pause_max_seconds:
            raise ValueError("朋友圈停留时间范围无效")
        if not self.pause_min_seconds <= self.pause_center_seconds <= self.pause_max_seconds:
            raise ValueError("朋友圈停留时间中心值超出范围")
        if self.pause_stddev_seconds <= 0:
            raise ValueError("朋友圈停留时间标准差必须大于零")


@dataclass(frozen=True, slots=True)
class WalletSettings:
    enabled: bool = True
    capture_once_per_day: bool = True
    transaction_limit: int = 10
    max_bill_pages: int = 3

    def __post_init__(self) -> None:
        if not 1 <= self.transaction_limit <= 30:
            raise ValueError("微信账单记录条数必须位于 1 到 30 之间")
        if not 1 <= self.max_bill_pages <= 5:
            raise ValueError("微信账单最多翻页次数必须位于 1 到 5 之间")


@dataclass(frozen=True, slots=True)
class ChatSettings:
    enabled: bool = False
    send: bool = False
    friend_name: str = ""
    message_groups: tuple[tuple[str, ...], ...] = ()
    once_per_day: bool = True
    interval_min_seconds: float = 1.5
    interval_center_seconds: float = 2.75
    interval_max_seconds: float = 4.0
    interval_stddev_seconds: float = 0.42

    def __post_init__(self) -> None:
        if self.enabled and not self.friend_name.strip():
            raise ValueError("启用聊天后必须配置 friend_name")
        if self.send and not self.enabled:
            raise ValueError("真实发送必须先启用聊天流程")
        if self.send and not self.message_groups:
            raise ValueError("真实发送至少需要配置一组消息")
        if self.interval_min_seconds < 0 or self.interval_min_seconds > self.interval_max_seconds:
            raise ValueError("消息间隔范围无效")
        if not self.interval_min_seconds <= self.interval_center_seconds <= self.interval_max_seconds:
            raise ValueError("消息间隔中心值超出范围")
        if self.interval_stddev_seconds <= 0:
            raise ValueError("消息间隔标准差必须大于零")
        for group in self.message_groups:
            if not 1 <= len(group) <= 2:
                raise ValueError("每组消息只能包含一到两条")
            if any(not message.strip() for message in group):
                raise ValueError("聊天消息不能为空")
            if any(len(message) > 200 for message in group):
                raise ValueError("单条聊天消息不能超过 200 个字符")


@dataclass(frozen=True, slots=True)
class WechatSettings:
    runtime_config: Path
    device_id: str | None = None
    ocr_engine: str = "macos_vision"
    ocr_language: str = "zh-Hans"
    launch_wait_seconds: float = 5.0
    page_wait_seconds: float = 2.0
    root_attempts: int = 3
    randomize_view_order: bool = True
    stop_app_probability: float = 0.0
    behavior: Mapping[str, Any] = field(default_factory=dict)
    moments: MomentsSettings = field(default_factory=MomentsSettings)
    wallet: WalletSettings = field(default_factory=WalletSettings)
    chat: ChatSettings = field(default_factory=ChatSettings)

    def __post_init__(self) -> None:
        if self.launch_wait_seconds < 0 or self.page_wait_seconds < 0:
            raise ValueError("页面等待时间不能小于零")
        if not 1 <= self.root_attempts <= 8:
            raise ValueError("返回微信首页尝试次数必须位于 1 到 8 之间")
        if not 0 <= self.stop_app_probability <= 1:
            raise ValueError("停止微信概率必须位于 0 到 1 之间")
        if self.ocr_engine not in {"paddle", "macos_vision"}:
            raise ValueError("微信 OCR 引擎必须是 paddle 或 macos_vision")


def load_wechat_settings(path: str | Path) -> WechatSettings:
    """加载独立配置，运行器公共配置相对本文件解析。"""

    config_path = Path(path).resolve()
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("微信配置根节点必须是对象")

    runtime_value = str(raw.get("runtime_config", "automation.json"))
    runtime_path = Path(runtime_value)
    if not runtime_path.is_absolute():
        runtime_path = (config_path.parent / runtime_path).resolve()

    moments_raw = _object(raw.get("moments"), "moments")
    wallet_raw = _object(raw.get("wallet"), "wallet")
    chat_raw = _object(raw.get("chat"), "chat")
    behavior = _object(raw.get("behavior"), "behavior")
    message_groups = _message_groups(chat_raw.get("message_groups", ()))
    device_id = str(raw.get("device_id", "")).strip() or None
    _fill_distribution_defaults(
        moments_raw,
        minimum_key="swipes_min",
        center_key="swipes_center",
        maximum_key="swipes_max",
        stddev_key="swipes_stddev",
        default_minimum=2,
        default_maximum=5,
    )
    _fill_distribution_defaults(
        moments_raw,
        minimum_key="pause_min_seconds",
        center_key="pause_center_seconds",
        maximum_key="pause_max_seconds",
        stddev_key="pause_stddev_seconds",
        default_minimum=2.5,
        default_maximum=6.0,
    )
    interval_minimum = float(chat_raw.get("interval_min_seconds", 1.5))
    interval_maximum = float(chat_raw.get("interval_max_seconds", 4.0))
    interval_center = float(
        chat_raw.get("interval_center_seconds", (interval_minimum + interval_maximum) / 2)
    )
    interval_stddev = float(
        chat_raw.get(
            "interval_stddev_seconds",
            max((interval_maximum - interval_minimum) / 6, 0.001),
        )
    )

    return WechatSettings(
        runtime_config=runtime_path,
        device_id=device_id,
        ocr_engine=str(raw.get("ocr_engine", "macos_vision")),
        ocr_language=str(raw.get("ocr_language", "zh-Hans")),
        launch_wait_seconds=float(raw.get("launch_wait_seconds", 5.0)),
        page_wait_seconds=float(raw.get("page_wait_seconds", 2.0)),
        root_attempts=int(raw.get("root_attempts", 3)),
        randomize_view_order=bool(raw.get("randomize_view_order", True)),
        stop_app_probability=float(raw.get("stop_app_probability", 0.0)),
        behavior=behavior,
        moments=MomentsSettings(**moments_raw),
        wallet=WalletSettings(**wallet_raw),
        chat=ChatSettings(
            enabled=bool(chat_raw.get("enabled", False)),
            send=bool(chat_raw.get("send", False)),
            friend_name=str(chat_raw.get("friend_name", "")).strip(),
            message_groups=message_groups,
            once_per_day=bool(chat_raw.get("once_per_day", True)),
            interval_min_seconds=interval_minimum,
            interval_center_seconds=interval_center,
            interval_max_seconds=interval_maximum,
            interval_stddev_seconds=interval_stddev,
        ),
    )


def _object(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"微信配置 {name} 必须是对象")
    return dict(value)


def _message_groups(value: Any) -> tuple[tuple[str, ...], ...]:
    if value in (None, ()):
        return ()
    if not isinstance(value, list):
        raise ValueError("message_groups 必须是二维数组")
    groups: list[tuple[str, ...]] = []
    for group in value:
        if not isinstance(group, list):
            raise ValueError("message_groups 中的每组消息必须是数组")
        if any(not isinstance(message, str) for message in group):
            raise ValueError("聊天消息必须是字符串")
        groups.append(tuple(group))
    return tuple(groups)


def _fill_distribution_defaults(
    values: dict[str, Any],
    *,
    minimum_key: str,
    center_key: str,
    maximum_key: str,
    stddev_key: str,
    default_minimum: float,
    default_maximum: float,
) -> None:
    """旧配置只覆盖边界时，根据有效范围补齐正态参数。"""

    if minimum_key not in values and maximum_key not in values:
        return
    minimum = float(values.get(minimum_key, default_minimum))
    maximum = float(values.get(maximum_key, default_maximum))
    values.setdefault(center_key, (minimum + maximum) / 2)
    values.setdefault(stddev_key, max((maximum - minimum) / 6, 0.001))
