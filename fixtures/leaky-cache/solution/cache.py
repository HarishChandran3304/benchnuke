"""Reference cache: TTL, no caching of failures, lock."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any


class Cache:
    def __init__(self, backend: Callable[[Any], Any], ttl: float = 60) -> None:
        self._backend = backend
        self._ttl = ttl
        self._lock = threading.Lock()
        self._store: dict[Any, tuple[Any, float]] = {}

    def get(self, key: Any) -> Any:
        now = time.monotonic()
        with self._lock:
            hit = self._store.get(key)
            if hit is not None:
                value, expires = hit
                if now < expires:
                    return value
                del self._store[key]
        value = self._backend(key)
        with self._lock:
            self._store[key] = (value, time.monotonic() + self._ttl)
        return value
