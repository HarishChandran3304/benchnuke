"""Multi-run dashboard aggregation (snapshot_runs) and the Textual app."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import DataTable, Static

from benchnuke.models import (
    AuditDocument,
    CoverageLevel,
    CoverageRow,
    Finding,
    FindingStatus,
    StageRecord,
    TaskRef,
)
from benchnuke.report import save_audit_document
from benchnuke.watch import snapshot_runs
from benchnuke.watch_tui import AuditWatchApp, DashboardScreen, RunDetailScreen


def _write_run(base: Path, rel: str, doc: AuditDocument) -> None:
    save_audit_document(base / rel / "results" / "audit.json", doc)


def _doc(
    task_id: str,
    status: str,
    stages: list[StageRecord],
    findings: list[Finding] | None = None,
    coverage: list[CoverageRow] | None = None,
) -> AuditDocument:
    return AuditDocument(
        task=TaskRef(id=task_id),
        run_status=status,
        current_stage=stages[-1].name if stages else None,
        stages=stages,
        findings=findings or [],
        coverage=coverage or [],
    )


def test_snapshot_runs_aggregates(tmp_path: Path) -> None:
    base = tmp_path / "audits"
    _write_run(
        base,
        "task-a",
        _doc(
            "bench/task-a",
            "running",
            [
                StageRecord(name="spec-extract", status="ok"),
                StageRecord(name="attack-R1", status="ok"),
                StageRecord(name="countertest-R1", status="running"),
            ],
            findings=[Finding(id="F001", requirement_id="R1", status=FindingStatus.CONFIRMED)],
            coverage=[
                CoverageRow(requirement_id="R1", coverage=CoverageLevel.NONE),
                CoverageRow(requirement_id="R2", coverage=CoverageLevel.PARTIAL),
                CoverageRow(requirement_id="R3", coverage=CoverageLevel.FULL),
            ],
        ),
    )
    _write_run(
        base,
        "task-b",
        _doc("bench/task-b", "completed", [StageRecord(name="report", status="ok")]),
    )
    rows = snapshot_runs(base)
    assert {row.task_id for row in rows} == {"bench/task-a", "bench/task-b"}
    running = rows[0]
    assert running.task_id == "bench/task-a"
    assert (running.stages_done, running.stages_total) == (2, 3)
    assert (running.attacks_done, running.attacks_total) == (1, 2)
    assert (running.confirmed, running.probable, running.rejected) == (1, 0, 0)
    done = next(row for row in rows if row.task_id == "bench/task-b")
    assert done.attacks_total == 0


def test_snapshot_runs_tolerates_corrupt_and_nested(tmp_path: Path) -> None:
    base = tmp_path / "audits"
    bad = base / "task-c" / "results"
    bad.mkdir(parents=True)
    (bad / "audit.json").write_text('{"task": incomplete', encoding="utf-8")
    _write_run(
        base,
        "deep/audit-pi",
        _doc("bench/task-d", "running", [StageRecord(name="spec-extract", status="ok")]),
    )
    rows = snapshot_runs(base)
    ids = {row.task_id for row in rows}
    assert "(busy)" in ids
    assert "bench/task-d" in ids


def test_snapshot_runs_empty_base(tmp_path: Path) -> None:
    assert snapshot_runs(tmp_path / "nope") == []


def test_dashboard_enter_drills_down_and_escape_returns(tmp_path: Path) -> None:
    base = tmp_path / "audits"
    _write_run(
        base,
        "task-a",
        _doc("bench/task-a", "running", [StageRecord(name="attack-R1", status="running")]),
    )
    _write_run(
        base,
        "task-b",
        _doc("bench/task-b", "completed", [StageRecord(name="report", status="ok")]),
    )

    async def scenario() -> None:
        app = AuditWatchApp(None, base=base, refresh=999.0)
        async with app.run_test() as pilot:
            assert isinstance(app.screen, DashboardScreen)
            assert app.screen.query_one(DataTable).row_count == 2
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, RunDetailScreen)
            summary = str(app.screen.query_one("#summary", Static).content)
            assert "bench/task-a" in summary
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, DashboardScreen)

    asyncio.run(scenario())


def test_open_with_work_dir_goes_straight_to_detail(tmp_path: Path) -> None:
    base = tmp_path / "audits"
    _write_run(
        base,
        "task-a",
        _doc("bench/task-a", "running", [StageRecord(name="attack-R1", status="running")]),
    )

    async def scenario() -> None:
        app = AuditWatchApp(base / "task-a", base=base, refresh=999.0)
        async with app.run_test() as pilot:
            assert isinstance(app.screen, RunDetailScreen)
            await pilot.press("escape")
            assert isinstance(app.screen, DashboardScreen)

    asyncio.run(scenario())
