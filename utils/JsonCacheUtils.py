import json
import os
import time
from typing import Any

# 将该文件和生成的 cache.json 一并提交到 git，即可跨机器共享
DEFAULT_CACHE_PATH = os.path.join(os.path.dirname(__file__), "cache.json")


class JsonCacheUtils:

    @staticmethod
    def _get_path(cache_path: str | None = None) -> str:
        """
        解析缓存文件路径：
        - None -> 默认 utils/cache.json
        - 仅传文件名（如 "config" 或 "config.json"）-> 放在 utils 目录下，自动补 .json
        - 传相对/绝对路径时保持原样，若无后缀则补 .json
        """
        if not cache_path:
            return DEFAULT_CACHE_PATH

        # 仅文件名（无路径分隔符）
        if os.sep not in cache_path:
            name = cache_path
            if not os.path.splitext(name)[1]:
                name += ".json"
            return os.path.join(os.path.dirname(__file__), name)

        # 具有路径的情况，尽量保留原意，只做后缀补全
        if not os.path.splitext(cache_path)[1]:
            return cache_path + ".json"
        return cache_path

    @staticmethod
    def _load(cache_path: str | None = None) -> dict:
        path = JsonCacheUtils._get_path(cache_path)
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _save(data: dict, cache_path: str | None = None) -> None:
        path = JsonCacheUtils._get_path(cache_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
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
    def set_flag(key: str, value: Any, *, cache_path: str | None = None) -> None:
        """写入一个标记，随 git 提交即可同步到其他环境。"""
        data = JsonCacheUtils._load(cache_path)
        ts = int(time.time())  # 秒级时间戳
        data[key] = {"value": value, "ts_str": JsonCacheUtils._format_ts(ts)}
        JsonCacheUtils._save(data, cache_path)

    @staticmethod
    def get_flag(key: str, default: Any = None, *, cache_path: str | None = None) -> Any:
        """读取标记；不存在则返回 default。"""
        return JsonCacheUtils._load(cache_path).get(key, default)

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
    def set_flag_today(key: str, value: Any, *, cache_path: str | None = None) -> None:
        """
        将某标记写成“今天”的值（仍旧是持久化 JSON）。
        - 若已有值且不是今天，则不覆盖，只提示跳过。
        """
        data = JsonCacheUtils._load(cache_path)
        entry = data.get(key)
        if entry and not JsonCacheUtils._is_same_day(
            ts=entry.get("ts"), ts_str=entry.get("ts_str")
        ):
            ts_readable = entry.get("ts_str") or JsonCacheUtils._format_ts(entry.get("ts"))
            print(f"[cache] skip set_today {key}, exists at {ts_readable} (not today)")
            return

        JsonCacheUtils.set_flag(key, value, cache_path=cache_path)
        print(f"[cache] set today {key} -> {value}")

    @staticmethod
    def get_flag_today(
        key: str,
        default: Any = None,
        *,
        cache_path: str | None = None,
        log: bool = True,
    ) -> Any:
        """
        读取“当天”的标记：
        - 如果存在且时间戳是今天，返回其 value
        - 否则返回 default
        """
        data = JsonCacheUtils._load(cache_path).get(key)
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
    def prune(
        max_age_days: int = 14,
        *,
        cache_path: str | None = None,
        now: float | None = None,
        log: bool = True,
    ) -> int:
        """
        清理超过 max_age_days 的缓存条目。
        Returns: 删除的条目数量。
        """
        data = JsonCacheUtils._load(cache_path)
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
            JsonCacheUtils._save(data, cache_path)
        if log:
            print(f"[cache] prune done, removed={removed}, max_age_days={max_age_days}")
        return removed
