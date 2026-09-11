"""Load a Harbor task directory into AuditTask."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from benchnuke.errors import TaskIngestError


class AuditTask(BaseModel):
    """Normalized Harbor task. Agents and graders consume this, not DeepSWE types."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    task_id: str
    root: Path
    instruction: str
    instruction_path: Path
    tests_dir: Path
    environment_dir: Path | None
    solution_dir: Path | None
    task_toml: dict[str, Any]
    has_reference_solution: bool
    source_format: str = "harbor"


def ingest_harbor_task(path: Path) -> AuditTask:
    root = path.expanduser().resolve()
    if not root.is_dir():
        raise TaskIngestError(f"task path is not a directory: {path}")

    instruction_path = root / "instruction.md"
    if not instruction_path.is_file():
        raise TaskIngestError(f"missing instruction.md in {root}")

    tests_dir = root / "tests"
    if not tests_dir.is_dir():
        raise TaskIngestError(f"missing tests/ directory in {root}")

    toml_path = root / "task.toml"
    task_toml: dict[str, Any] = {}
    if toml_path.is_file():
        task_toml = tomllib.loads(toml_path.read_text(encoding="utf-8"))

    task_name = ""
    task_table = task_toml.get("task")
    if isinstance(task_table, dict):
        task_name = str(task_table.get("name") or "")
    task_id = task_name or root.name

    environment_dir = root / "environment"
    solution_dir = root / "solution"
    has_solution = solution_dir.is_dir() and any(solution_dir.iterdir())

    return AuditTask(
        task_id=task_id,
        root=root,
        instruction=instruction_path.read_text(encoding="utf-8"),
        instruction_path=instruction_path,
        tests_dir=tests_dir,
        environment_dir=environment_dir if environment_dir.is_dir() else None,
        solution_dir=solution_dir if has_solution else None,
        task_toml=task_toml,
        has_reference_solution=has_solution,
    )
