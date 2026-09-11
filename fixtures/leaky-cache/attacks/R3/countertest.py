#!/usr/bin/env python3
"""Counter-test: failed requests must not be cached.

Plain script. Harbor runs this as tests/countertest.py via a staged task.
"""

from cache import Cache


def main() -> int:
    calls = {"n": 0}

    def backend(key: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return "ok"

    cache = Cache(backend)
    try:
        cache.get("a")
    except RuntimeError as exc:
        if "boom" not in str(exc):
            return 1
    else:
        return 1
    if cache.get("a") != "ok":
        return 1
    if calls["n"] != 2:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
