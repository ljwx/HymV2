import json
import os
import time
from typing import Any

DEFAULT_CACHE_PATH = os.path.join(os.path.dirname(__file__), "cache.json")


class JsonCacheUtils:

    @staticmethod
    def _get_path(cache_path: str | None = None) -> str:
        if not cache_path:
            return DEFAULT_CACHE_PATH
        if os.sep not in cache_path:
            name = cache_path if cache_path.endswith(".json") else cache_path + ".json"
            return os.path.join(os.path.dirname(__file__), name)
        return cache_path if cache_path.endswith(".json") else cache_path + ".json"

    @staticmethod
    def _load(cache_path: str | None = None) -> dict:
        path = JsonCacheUtils._get_path(cache_path)
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            # 文件为空或内容无效时返回空字典
            return {}

    @staticmethod
    def _save(data: dict, cache_path: str | None = None) -> None:
        path = JsonCacheUtils._get_path(cache_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _today() -> str:
        return time.strftime("%Y-%m-%d")

    @staticmethod
    def _now_str() -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S")

    # =========================
    # 基础读写
    # =========================
    @staticmethod
    def set_flag(key: str, value: Any, *, cache_path: str | None = None) -> None:
        data = JsonCacheUtils._load(cache_path)
        data[key] = {"value": value, "ts_str": JsonCacheUtils._now_str()}
        JsonCacheUtils._save(data, cache_path)

    @staticmethod
    def get_flag(key: str, default: Any = None, *, cache_path: str | None = None) -> Any:
        return JsonCacheUtils._load(cache_path).get(key, default)

    # =========================
    # 按日期存储（支持历史记录）
    # =========================
    @staticmethod
    def set_flag_today(key: str, value: Any, *, cache_path: str | None = None) -> None:
        """
        按日期存储，今天已设置则跳过。
        数据结构: {key: {"2025-12-16": {"value": ..., "ts_str": ...}, ...}}
        """
        data = JsonCacheUtils._load(cache_path)
        today = JsonCacheUtils._today()

        if key not in data:
            data[key] = {}

        if today in data[key]:
            print(f"[cache] skip {key}, already set today")
            return

        data[key][today] = {"value": value, "ts_str": JsonCacheUtils._now_str()}
        JsonCacheUtils._save(data, cache_path)
        print(f"[cache] set {key}[{today}] -> {value}")

    @staticmethod
    def get_flag_today(key: str, default: Any = None, *, cache_path: str | None = None) -> Any:
        """获取今天的值"""
        entry = JsonCacheUtils._load(cache_path).get(key, {})
        today = JsonCacheUtils._today()
        if today in entry:
            return entry[today].get("value", default)
        return default

    @staticmethod
    def get_flag_history(key: str, *, cache_path: str | None = None) -> dict:
        """获取所有历史记录"""
        return JsonCacheUtils._load(cache_path).get(key, {})

    @staticmethod
    def get_flag_by_date(key: str, date: str, default: Any = None, *, cache_path: str | None = None) -> Any:
        """获取指定日期的值"""
        entry = JsonCacheUtils._load(cache_path).get(key, {})
        if date in entry:
            return entry[date].get("value", default)
        return default
