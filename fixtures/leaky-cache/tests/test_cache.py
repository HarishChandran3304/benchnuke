#!/usr/bin/env python3
"""Official verifier — only checks successful-response caching.

Plain script (not pytest). Harbor's test.sh runs this and writes reward.txt.
"""

from cache import Cache


def main() -> int:
    calls = {"n": 0}

    def backend(key: str) -> str:
        calls["n"] += 1
        return f"ok:{key}"

    cache = Cache(backend)
    if cache.get("a") != "ok:a":
        return 1
    if cache.get("a") != "ok:a":
        return 1
    if calls["n"] != 1:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
