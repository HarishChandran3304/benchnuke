from __future__ import annotations

from pathlib import Path

from benchnuke.agent.base import AgentResult, StageSpec
from benchnuke.ingest.harbor import AuditTask
from benchnuke.models import AuditDocument, Requirement, RequirementKind, TaskRef
from benchnuke.stages.base import AuditContext, run_llm_stage
from benchnuke.stages.countertest import CountertestStage
from benchnuke.stages.layout import WorkLayout


class RecordingRunner:
    def __init__(self) -> None:
        self.log_dirs: list[Path] = []

    def run(self, spec: StageSpec, log_dir: Path) -> AgentResult:
        self.log_dirs.append(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        return AgentResult(returncode=0, stdout="{}", stderr="", session_id=None)


def _ctx(work_root: Path, runner: RecordingRunner) -> AuditContext:
    task = AuditTask(
        task_id="bench/task",
        root=work_root,
        instruction="",
        instruction_path=work_root / "instruction.md",
        tests_dir=work_root / "tests",
        environment_dir=None,
        solution_dir=None,
        task_toml={},
        has_reference_solution=False,
    )
    return AuditContext(
        task=task,
        work=WorkLayout(work_root),
        backend=None,  # unused by these stages
        runner=runner,
        document=AuditDocument(task=TaskRef(id="bench/task")),
    )


def test_run_dir_uses_agent_prefix(tmp_path: Path) -> None:
    work = WorkLayout(tmp_path)
    assert work.run_dir("coverage") == tmp_path / "runs" / "agent-coverage"


def test_run_dir_existing_defaults_to_agent(tmp_path: Path) -> None:
    work = WorkLayout(tmp_path)
    resolved = work.run_dir_existing("spec-extract")
    assert resolved == tmp_path / "runs" / "agent-spec-extract"


def test_run_ok_finds_legacy_grok_marker(tmp_path: Path) -> None:
    work = WorkLayout(tmp_path)
    legacy = tmp_path / "runs" / "grok-countertest-R3"
    legacy.mkdir(parents=True)
    (legacy / "ok").write_text("1\n", encoding="utf-8")
    assert work.run_ok("countertest-R3") == legacy / "ok"
    assert work.run_ok("countertest-R3").is_file()


def test_run_ok_prefers_agent_dir(tmp_path: Path) -> None:
    work = WorkLayout(tmp_path)
    legacy = tmp_path / "runs" / "grok-coverage"
    legacy.mkdir(parents=True)
    (legacy / "ok").write_text("1\n", encoding="utf-8")
    primary = tmp_path / "runs" / "agent-coverage"
    primary.mkdir(parents=True)
    assert work.run_ok("coverage") == primary / "ok"


def test_countertest_done_sees_legacy_marker(tmp_path: Path) -> None:
    work_root = tmp_path / "run"
    legacy = work_root / "runs" / "grok-countertest-R3"
    legacy.mkdir(parents=True)
    (legacy / "ok").write_text("1\n", encoding="utf-8")
    stage = CountertestStage(
        Requirement(id="R3", statement="No caching.", kind=RequirementKind.EXPLICIT)
    )
    assert stage.done(_ctx(work_root, RecordingRunner()))


def test_run_llm_stage_writes_agent_dir(tmp_path: Path) -> None:
    work_root = tmp_path / "run"
    work_root.mkdir()
    runner = RecordingRunner()
    run_llm_stage(
        _ctx(work_root, runner),
        name="coverage",
        prompt_name="coverage.md",
        tools=(),
        max_turns=1,
    )
    log_dir = work_root / "runs" / "agent-coverage"
    assert runner.log_dirs == [log_dir]
    assert (log_dir / "ok").is_file()
