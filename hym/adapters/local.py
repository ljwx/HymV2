from __future__ import annotations

import hashlib
import json
import os
import random
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence, TypeVar
from uuid import uuid4

from hym.core.events import to_jsonable
from hym.core.models import ArtifactRef

T = TypeVar("T")


class SystemClock:
    def now(self) -> datetime:
        return datetime.now().astimezone()

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            import time

            time.sleep(seconds)


class SystemRandomSource:
    """允许注入种子复现一次执行中的随机决策。"""

    def __init__(self, seed: int | None = None) -> None:
        self._random = random.Random(seed)

    def random(self) -> float:
        return self._random.random()

    def uniform(self, start: float, end: float) -> float:
        return self._random.uniform(start, end)

    def normalvariate(self, center: float, stddev: float) -> float:
        return self._random.normalvariate(center, stddev)

    def randint(self, start: int, end: int) -> int:
        return self._random.randint(start, end)

    def choice(self, items: Sequence[T]) -> T:
        return self._random.choice(items)

    def shuffle(self, items: list[T]) -> None:
        self._random.shuffle(items)


class AtomicJsonStateStore:
    """通过同目录原子替换避免进程中断留下半个 JSON 文件。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()

    def get(self, namespace: str, key: str, default: T | None = None) -> T | None:
        with self._lock:
            return self._load().get(namespace, {}).get(key, default)

    def set(self, namespace: str, key: str, value: Any) -> None:
        with self._lock:
            data = self._load()
            data.setdefault(namespace, {})[key] = value
            self._save(data)

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self, data: MappingLike) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(to_jsonable(data), file, ensure_ascii=False, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_name, self.path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)


MappingLike = dict[str, Any]


class LocalArtifactStore:
    """按日期和类型保存诊断产物，事件中只保留引用。"""

    _EXTENSIONS = {
        "application/json": ".json",
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "application/octet-stream": ".bin",
    }

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def save_bytes(
        self,
        *,
        kind: str,
        content: bytes,
        media_type: str,
        name_hint: str | None = None,
    ) -> ArtifactRef:
        artifact_id = uuid4().hex
        date_dir = datetime.now().astimezone().strftime("%Y-%m-%d")
        extension = self._EXTENSIONS.get(media_type, ".bin")
        name = _safe_name(name_hint or kind)
        path = self.root / date_dir / _safe_name(kind) / f"{name}-{artifact_id}{extension}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return ArtifactRef(
            artifact_id=artifact_id,
            kind=kind,
            uri=str(path.resolve()),
            media_type=media_type,
            sha256=hashlib.sha256(content).hexdigest(),
            metadata={"size": len(content)},
        )


def _safe_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_." else "_" for char in value)
    return cleaned[:80] or "artifact"
