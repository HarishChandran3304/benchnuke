"""Read-only snapshot of an audit work dir for the watch TUI."""

from __future__ import annotations

import time
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


@dataclass(frozen=True)
class RunSummary:
    """One row of the multi-run dashboard."""

    work_dir: Path
    task_id: str
    run_status: str
    current_stage: str | None
    stages_done: int
    stages_total: int
    confirmed: int
    probable: int
    rejected: int
    attacks_done: int
    attacks_total: int
    age_seconds: float


def snapshot_work(work_dir: Path, *, tail_lines: int = 24) -> WatchSnapshot:
    layout = WorkLayout(work_dir)
    try:
        document = load_audit_document(layout.audit_json)
    except Exception:
        document = None
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


def snapshot_runs(base: Path = Path("audits")) -> list[RunSummary]:
    """Summarize every run under base, running first, then by activity."""
    if not base.is_dir():
        return []
    rows: list[tuple[float, RunSummary]] = []
    for path in base.rglob("audit.json"):
        rows.append((path.stat().st_mtime, _summarize_run(path)))
    rows.sort(key=lambda item: (item[1].run_status != "running", -item[0]))
    return [row for _, row in rows]


def _summarize_run(path: Path) -> RunSummary:
    work_dir = path.parent.parent
    try:
        document = load_audit_document(path)
    except Exception:
        document = None
    if document is None:
        return RunSummary(
            work_dir=work_dir,
            task_id="(busy)",
            run_status="unknown",
            current_stage=None,
            stages_done=0,
            stages_total=0,
            confirmed=0,
            probable=0,
            rejected=0,
            attacks_done=0,
            attacks_total=0,
            age_seconds=_age(path),
        )
    stages = document.stages
    counts = {"confirmed": 0, "probable": 0, "rejected": 0}
    for finding in document.findings:
        if finding.status.value in counts:
            counts[finding.status.value] += 1
    attacks_done = len(
        {
            row.name
            for row in stages
            if row.name.startswith("attack-") and row.status in {"ok", "skip"}
        }
    )
    attacks_total = sum(
        1 for row in document.coverage if row.coverage.value in {"none", "partial"}
    )
    return RunSummary(
        work_dir=work_dir,
        task_id=document.task.id,
        run_status=document.run_status,
        current_stage=document.current_stage,
        stages_done=sum(1 for row in stages if row.status in {"ok", "skip"}),
        stages_total=len(stages),
        confirmed=counts["confirmed"],
        probable=counts["probable"],
        rejected=counts["rejected"],
        attacks_done=attacks_done,
        attacks_total=attacks_total,
        age_seconds=_age(path),
    )


def _age(path: Path) -> float:
    stat = path.stat()
    start = getattr(stat, "st_birthtime", stat.st_mtime)
    return max(0.0, time.time() - start)


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
