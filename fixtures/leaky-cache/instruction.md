# In-memory response cache

Implement a Python module `cache.py` that exports a `Cache` class.

`Cache(backend, ttl=60)` wraps a callable `backend(key) -> value`.

Requirements:

1. Cache successful responses. A second `get` for the same key must not call `backend` again while the entry is live.
2. Entries expire after 60 seconds (the default `ttl`).
3. Failed requests must not be cached. If `backend` raises, a later `get` for that key must call `backend` again.
4. The implementation must be thread-safe.

`get(key)` returns the value or re-raises the backend exception.
