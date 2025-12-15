import json
import os
import time
from typing import Any

# 将该文件和生成的 cache.json 一并提交到 git，即可跨机器共享
CACHE_PATH = os.path.join(os.path.dirname(__file__), "cache.json")


class JsonCacheUtils:

    @staticmethod
    def _load() -> dict:
        if not os.path.exists(CACHE_PATH):
            return {}
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _save(data: dict) -> None:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _format_ts(ts: int | None) -> str:
        if ts is None:
            return "unknown"
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))

    @staticmethod
    def _parse_ts_str(ts_str: str | None) -> int | None:
        """将 ts_str 解析为时间戳秒；失败返回 None。"""
        if not ts_str:
            return None
        try:
            return int(time.mktime(time.strptime(ts_str, "%Y-%m-%d %H:%M:%S")))
        except Exception:
            return None

    @staticmethod
    def _entry_ts(entry: dict) -> int | None:
        """从缓存条目中获取时间戳（优先旧字段 ts，其次 ts_str）。"""
        if not entry:
            return None
        ts = entry.get("ts")  # 兼容旧数据
        if ts is not None:
            return ts
        return JsonCacheUtils._parse_ts_str(entry.get("ts_str"))

    @staticmethod
    def set_flag(key: str, value: Any) -> None:
        """写入一个标记，随 git 提交即可同步到其他环境。"""
        data = JsonCacheUtils._load()
        ts = int(time.time())  # 秒级时间戳
        data[key] = {"value": value, "ts_str": JsonCacheUtils._format_ts(ts)}
        JsonCacheUtils._save(data)

    @staticmethod
    def get_flag(key: str, default: Any = None) -> Any:
        """读取标记；不存在则返回 default。"""
        return JsonCacheUtils._load().get(key, default)

    # =========================
    # 便捷的“当天”读写辅助
    # =========================
    @staticmethod
    def _is_same_day(ts: int | None = None, ts_str: str | None = None, now: float | None = None) -> bool:
        """
        同一天判断：
        - 优先用 ts（秒级时间戳）
        - 否则尝试解析 ts_str（格式 YYYY-MM-DD HH:MM:SS）
        """
        if ts is None and ts_str:
            ts = JsonCacheUtils._parse_ts_str(ts_str)
        if ts is None:
            return False
        if now is None:
            now = time.time()
        return time.localtime(ts)[:3] == time.localtime(now)[:3]

    @staticmethod
    def set_flag_today(key: str, value: Any) -> None:
        """
        将某标记写成“今天”的值（仍旧是持久化 JSON）。
        """
        JsonCacheUtils.set_flag(key, value)
        print(f"[cache] set today {key} -> {value}")

    @staticmethod
    def get_flag_today(key: str, default: Any = None, *, log: bool = True) -> Any:
        """
        读取“当天”的标记：
        - 如果存在且时间戳是今天，返回其 value
        - 否则返回 default
        """
        data = JsonCacheUtils._load().get(key)
        if not data:
            if log:
                print(f"[cache] miss {key}, return default")
            return default

        ts = data.get("ts")  # 兼容旧数据；新数据已不再保存 ts
        ts_str = data.get("ts_str")
        if JsonCacheUtils._is_same_day(ts=ts, ts_str=ts_str):
            return data.get("value", default)

        if log:
            ts_readable = ts_str or JsonCacheUtils._format_ts(ts)
            print(f"[cache] {key} exists but not today (ts={ts_readable}), return default")
        return default

    @staticmethod
    def prune(max_age_days: int = 14, *, now: float | None = None, log: bool = True) -> int:
        """
        清理超过 max_age_days 的缓存条目。
        Returns: 删除的条目数量。
        """
        data = JsonCacheUtils._load()
        if not data:
            return 0
        if now is None:
            now = time.time()
        threshold = now - max_age_days * 86400

        removed = 0
        for key in list(data.keys()):
            ts = JsonCacheUtils._entry_ts(data.get(key))
            if ts is not None and ts < threshold:
                removed += 1
                del data[key]

        if removed > 0:
            JsonCacheUtils._save(data)
        if log:
            print(f"[cache] prune done, removed={removed}, max_age_days={max_age_days}")
        return removed
