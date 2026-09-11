"""Adversarial cache: caches exceptions, no TTL, no lock."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class Cache:
    def __init__(self, backend: Callable[[Any], Any], ttl: float = 60) -> None:
        self._backend = backend
        self._store: dict[Any, Any] = {}

    def get(self, key: Any) -> Any:
        if key not in self._store:
            try:
                self._store[key] = self._backend(key)
            except Exception as exc:
                self._store[key] = exc
                raise
        value = self._store[key]
        if isinstance(value, Exception):
            raise value
        return value
