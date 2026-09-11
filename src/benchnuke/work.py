"""Work-directory layout."""

from __future__ import annotations

from pathlib import Path


def default_work_dir(task_id: str, base: Path | None = None) -> Path:
    root = base or Path("audits")
    safe = task_id.replace("/", "__")
    return root / safe
