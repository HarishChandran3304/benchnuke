"""Harbor task ingestion."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchnuke.errors import TaskIngestError
from benchnuke.ingest.harbor import ingest_harbor_task


def _write_minimal_task(root: Path, *, instruction: str = "Do the thing.\n") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "instruction.md").write_text(instruction, encoding="utf-8")
    (root / "task.toml").write_text(
        """
schema_version = "1.0"

[task]
name = "benchnuke/leaky-cache"
""".lstrip(),
        encoding="utf-8",
    )
    tests = root / "tests"
    tests.mkdir()
    (tests / "test.sh").write_text(
        "#!/bin/sh\necho 1 > /logs/verifier/reward.txt\n",
        encoding="utf-8",
    )
    env = root / "environment"
    env.mkdir()
    (env / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    return root


def test_ingest_reads_instruction_and_tests(tmp_path: Path) -> None:
    task_dir = _write_minimal_task(
        tmp_path / "task",
        instruction="Cache must not store failures.\n",
    )
    artifact = ingest_harbor_task(task_dir)
    assert artifact.instruction.strip() == "Cache must not store failures."
    assert artifact.task_id == "benchnuke/leaky-cache"
    assert artifact.tests_dir == task_dir / "tests"
    assert artifact.instruction_path == task_dir / "instruction.md"
    assert artifact.has_reference_solution is False


def test_ingest_detects_reference_solution(tmp_path: Path) -> None:
    task_dir = _write_minimal_task(tmp_path / "task")
    solution = task_dir / "solution"
    solution.mkdir()
    (solution / "solve.sh").write_text("#!/bin/sh\ntrue\n", encoding="utf-8")
    artifact = ingest_harbor_task(task_dir)
    assert artifact.has_reference_solution is True
    assert artifact.solution_dir == solution


def test_ingest_fails_without_instruction(tmp_path: Path) -> None:
    task_dir = _write_minimal_task(tmp_path / "task")
    (task_dir / "instruction.md").unlink()
    with pytest.raises(TaskIngestError, match="instruction.md"):
        ingest_harbor_task(task_dir)


def test_ingest_fails_without_tests(tmp_path: Path) -> None:
    task_dir = _write_minimal_task(tmp_path / "task")
    for child in (task_dir / "tests").iterdir():
        child.unlink()
    (task_dir / "tests").rmdir()
    with pytest.raises(TaskIngestError, match="tests"):
        ingest_harbor_task(task_dir)


def test_ingest_fails_on_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(TaskIngestError, match="not a directory"):
        ingest_harbor_task(tmp_path / "nope")
