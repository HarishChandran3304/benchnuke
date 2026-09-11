"""Bounded retry/self-heal for operational stage failures in maybe_run."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from benchnuke.errors import (
    AgentRunnerError,
    GradeError,
    SchemaError,
    TaskIngestError,
    is_retryable,
)
from benchnuke.ingest.harbor import ingest_harbor_task
from benchnuke.models import AuditDocument, TaskRef
from benchnuke.stages.base import AuditContext, maybe_run
from benchnuke.stages.layout import WorkLayout


class ScriptedStage:
    """Stage that raises its queued errors in order, then succeeds."""

    def __init__(self, errors: list[Exception], name: str = "scripted") -> None:
        self.name = name
        self.errors = list(errors)
        self.attempts = 0

    def done(self, ctx: AuditContext) -> bool:
        return False

    def run(self, ctx: AuditContext) -> None:
        self.attempts += 1
        if self.errors:
            raise self.errors.pop(0)


def make_ctx(tmp_path: Path) -> AuditContext:
    task_root = tmp_path / "task"
    (task_root / "tests").mkdir(parents=True)
    (task_root / "instruction.md").write_text("Do the thing.\n", encoding="utf-8")
    work = WorkLayout(tmp_path / "work")
    work.root.mkdir(parents=True)
    document = AuditDocument(task=TaskRef(id="bench/task"), work_dir=str(work.root))
    return AuditContext(
        task=ingest_harbor_task(task_root),
        work=work,
        backend=object(),  # type: ignore[arg-type]
        runner=object(),  # type: ignore[arg-type]
        document=document,
        deadline_monotonic=time.monotonic() + 3600,
    )


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    recorded: list[float] = []
    monkeypatch.setattr(time, "sleep", recorded.append)
    return recorded


def test_retryable_error_then_success_is_retried(sleeps: list[float], tmp_path: Path) -> None:
    ctx = make_ctx(tmp_path)
    stage = ScriptedStage([SchemaError("spec-extract did not write requirements.json")])
    assert maybe_run(stage, ctx) == "run"
    assert stage.attempts == 2
    assert sleeps == [5.0]
    record = ctx.document.stages[-1]
    assert (record.name, record.status, record.error) == ("scripted", "ok", None)
    assert ctx.document.run_status == "running"


def test_retryable_error_exhausts_three_attempts(sleeps: list[float], tmp_path: Path) -> None:
    ctx = make_ctx(tmp_path)
    stage = ScriptedStage([AgentRunnerError("pi -p timed out for stage x after 9s")] * 3)
    with pytest.raises(AgentRunnerError):
        maybe_run(stage, ctx)
    assert stage.attempts == 3
    assert sleeps == [5.0, 15.0]
    record = ctx.document.stages[-1]
    assert record.status == "error"
    assert record.error is not None
    assert "failed after 3 attempts" in record.error
    assert ctx.document.run_status == "failed"


@pytest.mark.parametrize("marker", ["reference_inconsistency", "verifier_infrastructure"])
def test_finding_grade_error_is_never_retried(
    sleeps: list[float], tmp_path: Path, marker: str
) -> None:
    ctx = make_ctx(tmp_path)
    stage = ScriptedStage([GradeError(f"bench/task: sanity check failed ({marker})")])
    with pytest.raises(GradeError):
        maybe_run(stage, ctx)
    assert stage.attempts == 1
    assert sleeps == []
    assert ctx.document.stages[-1].status == "error"
    assert ctx.document.run_status == "failed"


def test_retry_not_started_past_deadline(sleeps: list[float], tmp_path: Path) -> None:
    ctx = make_ctx(tmp_path)

    class DeadlineEater(ScriptedStage):
        def run(self, ctx: AuditContext) -> None:
            ctx.deadline_monotonic = time.monotonic() - 1
            super().run(ctx)

    stage = DeadlineEater([SchemaError("coverage stage did not write coverage.json")])
    with pytest.raises(SchemaError):
        maybe_run(stage, ctx)
    assert stage.attempts == 1
    assert sleeps == []


def test_is_retryable_taxonomy() -> None:
    assert is_retryable(SchemaError("spec-extract did not write requirements.json"))
    assert is_retryable(AgentRunnerError("pi -p timed out for stage spec after 9s"))
    assert is_retryable(AgentRunnerError("pi -p failed for stage spec (exit 1)"))
    assert is_retryable(GradeError("harbor run failed (exit 1). boom"))
    assert is_retryable(GradeError("no Harbor verifier reward under /tmp/jobs"))
    assert is_retryable(GradeError("anything", retryable=True))
    assert is_retryable(subprocess.TimeoutExpired(cmd=["harbor"], timeout=1))
    assert is_retryable(TimeoutError("socket timed out"))
    assert not is_retryable(GradeError("gold failed (reference_inconsistency)"))
    assert not is_retryable(GradeError("nop passed (verifier_infrastructure)"))
    assert not is_retryable(GradeError("harbor binary not found: harbor"))
    assert not is_retryable(GradeError("anything", retryable=False))
    assert not is_retryable(AgentRunnerError("pi binary not found: pi"))
    assert not is_retryable(AgentRunnerError("bn audit exceeded 60s wall clock"))
    assert not is_retryable(TaskIngestError("missing instruction.md"))
    assert not is_retryable(ValueError("nope"))
    assert not is_retryable(AgentRunnerError("audit time budget exceeded before stage x"))


def test_maybe_run_refuses_stage_past_deadline(tmp_path: Path) -> None:
    ctx = make_ctx(tmp_path)
    ctx.deadline_monotonic = time.monotonic() - 1
    stage = ScriptedStage([])
    with pytest.raises(AgentRunnerError, match="time budget"):
        maybe_run(stage, ctx)
    assert stage.attempts == 0
    record = ctx.document.stages[-1]
    assert record.status == "error"
    assert record.error == "audit time budget exceeded"
    assert ctx.document.run_status == "failed"
