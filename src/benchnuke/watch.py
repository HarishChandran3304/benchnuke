"""Read-only snapshot of an audit work dir for the watch TUI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from benchnuke.models import StageRecord
from benchnuke.report import load_audit_document
from benchnuke.stages.layout import WorkLayout


@dataclass(frozen=True)
class WatchSnapshot:
    task_id: str
    run_status: str
    current_stage: str | None
    work_dir: Path
    stages: list[StageRecord]
    log_path: Path | None
    log_tail: str


def snapshot_work(work_dir: Path, *, tail_lines: int = 24) -> WatchSnapshot:
    layout = WorkLayout(work_dir)
    document = load_audit_document(layout.audit_json)
    if document is None:
        return WatchSnapshot(
            task_id="(no audit.json)",
            run_status="unknown",
            current_stage=None,
            work_dir=work_dir,
            stages=[],
            log_path=None,
            log_tail="waiting for audit.json…",
        )
    stage = document.current_stage
    log_path = log_path_for_stage(work_dir, stage) if stage else None
    return WatchSnapshot(
        task_id=document.task.id,
        run_status=document.run_status,
        current_stage=stage,
        work_dir=work_dir,
        stages=list(document.stages),
        log_path=log_path,
        log_tail=_tail(log_path, tail_lines),
    )


def log_path_for_stage(work_dir: Path, stage_name: str) -> Path | None:
    layout = WorkLayout(work_dir)
    candidates = [
        layout.run_dir_existing(stage_name) / "stdout.log",
        layout.run_dir_existing(stage_name) / "stderr.log",
        layout.preflight / "oracle-gold" / "stdout.log",
        layout.preflight / "nop" / "stdout.log",
    ]
    if stage_name.startswith("sanity"):
        candidates = [
            layout.preflight / "oracle-gold" / "stdout.log",
            layout.preflight / "nop" / "stdout.log",
            *candidates,
        ]
    for path in candidates:
        if path.is_file() and path.stat().st_size > 0:
            return path
    search_roots = [layout.run_dir_existing(stage_name)]
    if stage_name.startswith("prove-"):
        search_roots.extend(
            [
                work_dir / "runs" / "prove-adv",
                work_dir / "runs" / "grade-adv",
                work_dir / "runs" / "grade-gold",
            ]
        )
    logs: list[Path] = []
    for root in search_roots:
        if root.is_dir():
            logs.extend(root.rglob("*.log"))
    if logs:
        logs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return logs[0]
    return None


def find_latest_work(*, base: Path | None = None) -> Path | None:
    root = base or Path("audits")
    if not root.is_dir():
        return None
    newest: tuple[float, Path] | None = None
    for path in root.rglob("audit.json"):
        mtime = path.stat().st_mtime
        work = path.parent.parent
        if newest is None or mtime > newest[0]:
            newest = (mtime, work)
    return None if newest is None else newest[1]


def _tail(path: Path | None, n: int) -> str:
    if path is None or not path.is_file():
        return "(no log for this stage yet)"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "(could not read log)"
    if not lines:
        return "(empty log)"
    return "\n".join(lines[-n:])
