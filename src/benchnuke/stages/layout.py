"""Work-directory paths for a resumable audit."""

from __future__ import annotations

import json
from pathlib import Path

RUN_DIR_PREFIX = "agent"
LEGACY_RUN_DIR_PREFIX = "grok"


class WorkLayout:
    def __init__(self, root: Path) -> None:
        self.root = root

    @property
    def context(self) -> Path:
        return self.root / "context.md"

    @property
    def requirements(self) -> Path:
        return self.root / "requirements.json"

    @property
    def coverage(self) -> Path:
        return self.root / "coverage.json"

    @property
    def empty(self) -> Path:
        return self.root / "empty"

    @property
    def stage0(self) -> Path:
        return self.root / "stage0"

    @property
    def stage0_ok(self) -> Path:
        return self.stage0 / "ok"

    @property
    def audit_output(self) -> Path:
        return self.root / "audit-output"

    @property
    def audit_json(self) -> Path:
        return self.audit_output / "audit.json"

    def artifact(self, req_id: str) -> Path:
        return self.root / "artifacts" / req_id

    def official_grade(self, req_id: str) -> Path:
        return self.artifact(req_id) / "official.json"

    def countertest(self, req_id: str) -> Path:
        return self.artifact(req_id) / "countertest.py"

    def prove_ok(self, req_id: str) -> Path:
        return self.artifact(req_id) / "prove.json"

    def run_dir(self, stage_name: str) -> Path:
        """Canonical run dir for new writes: runs/agent-<stage>."""
        return self.root / "runs" / f"{RUN_DIR_PREFIX}-{stage_name}"

    def legacy_run_dir(self, stage_name: str) -> Path:
        """Run dir name used by runs started before the Pi harness rename."""
        return self.root / "runs" / f"{LEGACY_RUN_DIR_PREFIX}-{stage_name}"

    def run_dir_existing(self, stage_name: str) -> Path:
        """Resolve a stage's run dir: prefer agent-, fall back to legacy grok-."""
        primary = self.run_dir(stage_name)
        if primary.is_dir():
            return primary
        legacy = self.legacy_run_dir(stage_name)
        if legacy.is_dir():
            return legacy
        return primary

    def run_ok(self, stage_name: str) -> Path:
        return self.run_dir_existing(stage_name) / "ok"


def find_run_for_task(task_id: str, *, base: Path | None = None) -> Path | None:
    """Newest work dir whose audit.json names this task id."""
    root = base or Path("work")
    if not root.is_dir():
        return None
    matches: list[tuple[float, Path]] = []
    for path in root.rglob("audit.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        task = payload.get("task")
        if not isinstance(task, dict) or task.get("id") != task_id:
            continue
        matches.append((path.stat().st_mtime, path.parent.parent))
    if not matches:
        return None
    matches.sort(key=lambda item: item[0], reverse=True)
    return matches[0][1]
