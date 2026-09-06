"""Content-hashed local cache to avoid redundant worker-model calls.

Cache key = sha256(task_kind + provider_model_id + normalized_input).
Storing the model id in the key means switching providers naturally
invalidates stale cache entries instead of serving mismatched output.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass
class CacheEntry:
    key: str
    result: str
    created_at: float
    task_kind: str
    model_id: str


class ContentCache:
    def __init__(self, directory: str | Path, ttl_seconds: int, enabled: bool = True):
        self.directory = Path(directory)
        self.ttl_seconds = ttl_seconds
        self.enabled = enabled
        if self.enabled:
            self.directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def compute_key(task_kind: str, model_id: str, content: str, extra: Optional[dict] = None) -> str:
        hasher = hashlib.sha256()
        hasher.update(task_kind.encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update(model_id.encode("utf-8"))
        hasher.update(b"\x00")
        if extra:
            hasher.update(json.dumps(extra, sort_keys=True).encode("utf-8"))
            hasher.update(b"\x00")
        hasher.update(content.encode("utf-8"))
        return hasher.hexdigest()

    def _path_for(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def get(self, key: str) -> Optional[str]:
        if not self.enabled:
            return None
        path = self._path_for(key)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        age = time.time() - data.get("created_at", 0)
        if age > self.ttl_seconds:
            path.unlink(missing_ok=True)
            return None
        return data.get("result")

    def set(self, key: str, result: str, task_kind: str, model_id: str) -> None:
        if not self.enabled:
            return
        entry = {
            "key": key,
            "result": result,
            "created_at": time.time(),
            "task_kind": task_kind,
            "model_id": model_id,
        }
        self._path_for(key).write_text(json.dumps(entry), encoding="utf-8")

    def clear(self) -> int:
        if not self.enabled or not self.directory.is_dir():
            return 0
        count = 0
        for f in self.directory.glob("*.json"):
            f.unlink()
            count += 1
        return count
