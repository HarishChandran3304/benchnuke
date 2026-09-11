"""Stage retry feedback: a failed attempt's parse error reaches the next prompt."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from benchnuke.agent.base import AgentResult
from benchnuke.ingest.harbor import ingest_harbor_task
from benchnuke.models import AuditDocument, TaskRef
from benchnuke.stages.base import AuditContext, maybe_run
from benchnuke.stages.layout import WorkLayout
from benchnuke.stages.spec import SpecStage


class _FlakySpecWriter:
    """Writes malformed requirements.json once, valid JSON on later calls."""

    def __init__(self) -> None:
        self.calls = 0
        self.prompts: list[str] = []

    def run(self, spec, log_dir: Path) -> AgentResult:
        self.calls += 1
        self.prompts.append(spec.prompt_file.read_text(encoding="utf-8"))
        log_dir.mkdir(parents=True, exist_ok=True)
        if self.calls == 1:
            (spec.cwd / "requirements.json").write_text(
                '{"requirements": [{"id": "R1", "statement": "track "http" scopes only"}]}',
                encoding="utf-8",
            )
        else:
            (spec.cwd / "requirements.json").write_text(
                json.dumps(
                    {"requirements": [{"id": "R1", "statement": "s", "kind": "explicit"}]}
                ),
                encoding="utf-8",
            )
        return AgentResult(returncode=0, stdout="{}", stderr="", session_id=None)


def _ctx(tmp_path: Path, runner) -> AuditContext:
    task_root = tmp_path / "task"
    (task_root / "tests").mkdir(parents=True)
    (task_root / "instruction.md").write_text("Do the thing.\n", encoding="utf-8")
    work = WorkLayout(tmp_path / "work")
    work.root.mkdir(parents=True)
    return AuditContext(
        task=ingest_harbor_task(task_root),
        work=work,
        backend=object(),  # type: ignore[arg-type]
        runner=runner,  # type: ignore[arg-type]
        document=AuditDocument(task=TaskRef(id="bench/task"), work_dir=str(work.root)),
        deadline_monotonic=time.monotonic() + 3600,
    )


def test_invalid_json_retries_with_error_feedback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    runner = _FlakySpecWriter()
    ctx = _ctx(tmp_path, runner)
    assert maybe_run(SpecStage(), ctx) == "run"
    assert runner.calls == 2
    assert ctx.document.stages[-1].status == "ok"
    assert ctx.document.specification[0].id == "R1"
    assert "{{error_feedback}}" not in runner.prompts[0]
    assert "previous attempt produced an invalid output file" in runner.prompts[1]
    assert "track " in runner.prompts[1]  # the offending content is quoted back
    feedback = ctx.work.root / "prompts" / "spec-extract.error.txt"
    assert not feedback.exists()
