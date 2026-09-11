from __future__ import annotations

from pathlib import Path

from benchnuke.models import AuditDocument, StageRecord, TaskRef
from benchnuke.report import save_audit_document
from benchnuke.watch import WatchSnapshot, log_path_for_stage, snapshot_work


def test_snapshot_reads_stages(tmp_path: Path) -> None:
    work = tmp_path / "run"
    doc = AuditDocument(
        task=TaskRef(id="bench/task"),
        run_status="running",
        current_stage="countertest-R29",
        work_dir=str(work),
        stages=[
            StageRecord(name="spec-extract", status="ok"),
            StageRecord(name="countertest-R29", status="running"),
        ],
    )
    save_audit_document(work / "results" / "audit.json", doc)
    snap = snapshot_work(work)
    assert snap.task_id == "bench/task"
    assert snap.run_status == "running"
    assert snap.current_stage == "countertest-R29"
    assert [row.name for row in snap.stages] == ["spec-extract", "countertest-R29"]


def test_log_path_prefers_stdout(tmp_path: Path) -> None:
    work = tmp_path / "run"
    log_dir = work / "runs" / "agent-countertest-R29"
    log_dir.mkdir(parents=True)
    (log_dir / "stdout.log").write_text("tool: bash\n", encoding="utf-8")
    path = log_path_for_stage(work, "countertest-R29")
    assert path == log_dir / "stdout.log"
    text = WatchSnapshot(
        task_id="t",
        run_status="running",
        current_stage="countertest-R29",
        work_dir=work,
        stages=[],
        log_path=path,
        log_tail="tool: bash\n",
    )
    assert "bash" in text.log_tail


def test_log_path_falls_back_to_legacy_grok_dir(tmp_path: Path) -> None:
    work = tmp_path / "run"
    log_dir = work / "runs" / "grok-countertest-R29"
    log_dir.mkdir(parents=True)
    (log_dir / "stdout.log").write_text("tool: bash\n", encoding="utf-8")
    path = log_path_for_stage(work, "countertest-R29")
    assert path == log_dir / "stdout.log"
