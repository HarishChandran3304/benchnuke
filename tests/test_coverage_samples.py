"""Coverage sampling: N independent passes merged most-suspicious-wins."""

from __future__ import annotations

import json
import time
from pathlib import Path

from benchnuke.agent.base import AgentResult
from benchnuke.ingest.harbor import ingest_harbor_task
from benchnuke.models import AuditDocument, CoverageLevel, CoverageRow, TaskRef
from benchnuke.stages.base import AuditContext
from benchnuke.stages.coverage import CoverageStage, merge_coverage_samples
from benchnuke.stages.layout import WorkLayout


def _row(req_id: str, level: CoverageLevel, gap: str = "") -> CoverageRow:
    return CoverageRow(requirement_id=req_id, coverage=level, suspected_gap=gap)


def test_merge_keeps_most_suspicious_row() -> None:
    s1 = [_row("R1", CoverageLevel.FULL), _row("R2", CoverageLevel.FULL)]
    s2 = [
        _row("R1", CoverageLevel.PARTIAL, "weak default-mode assertion"),
        _row("R2", CoverageLevel.NONE),
    ]
    s3 = [_row("R1", CoverageLevel.INDIRECT), _row("R2", CoverageLevel.FULL)]
    merged = {row.requirement_id: row for row in merge_coverage_samples([s1, s2, s3])}
    assert merged["R1"].coverage is CoverageLevel.PARTIAL
    assert merged["R1"].suspected_gap == "weak default-mode assertion"
    assert merged["R2"].coverage is CoverageLevel.NONE


def test_merge_unions_requirements_seen_in_any_sample() -> None:
    s1 = [_row("R1", CoverageLevel.FULL)]
    s2 = [_row("R2", CoverageLevel.PARTIAL)]
    merged = {row.requirement_id for row in merge_coverage_samples([s1, s2])}
    assert merged == {"R1", "R2"}


class _ScriptedCoverage:
    """Writes a different coverage.json per call, in order."""

    def __init__(self, payloads: list[list[dict]]) -> None:
        self.payloads = payloads
        self.calls = 0

    def run(self, spec, log_dir: Path) -> AgentResult:
        rows = self.payloads[min(self.calls, len(self.payloads) - 1)]
        self.calls += 1
        (spec.cwd / "coverage.json").write_text(
            json.dumps({"coverage": rows}), encoding="utf-8"
        )
        log_dir.mkdir(parents=True, exist_ok=True)
        return AgentResult(returncode=0, stdout="{}", stderr="", session_id=None)


def _ctx(tmp_path: Path) -> AuditContext:
    task_root = tmp_path / "task"
    (task_root / "tests").mkdir(parents=True)
    (task_root / "instruction.md").write_text("Do the thing.\n", encoding="utf-8")
    work = WorkLayout(tmp_path / "work")
    work.root.mkdir(parents=True)
    return AuditContext(
        task=ingest_harbor_task(task_root),
        work=work,
        backend=object(),  # type: ignore[arg-type]
        runner=object(),  # type: ignore[arg-type]
        document=AuditDocument(task=TaskRef(id="bench/task"), work_dir=str(work.root)),
        deadline_monotonic=time.monotonic() + 3600,
    )


def test_coverage_stage_samples_and_merges(tmp_path: Path) -> None:
    runner = _ScriptedCoverage(
        [
            [{"requirement_id": "R1", "coverage": "full"}],
            [{"requirement_id": "R1", "coverage": "partial"}],
            [{"requirement_id": "R1", "coverage": "full"}],
        ]
    )
    ctx = _ctx(tmp_path)
    ctx.runner = runner  # type: ignore[assignment]
    CoverageStage().run(ctx)
    assert runner.calls == 3
    rows = json.loads(ctx.work.coverage.read_text(encoding="utf-8"))["coverage"]
    assert len(rows) == 1
    assert rows[0]["requirement_id"] == "R1"
    assert rows[0]["coverage"] == "partial"
    assert ctx.document.coverage[0].coverage is CoverageLevel.PARTIAL
