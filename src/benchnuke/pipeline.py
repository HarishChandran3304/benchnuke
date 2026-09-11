"""Audit orchestration."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from benchnuke.classify import classify_finding
from benchnuke.context import write_context
from benchnuke.errors import SchemaError
from benchnuke.execute.base import VerifierBackend
from benchnuke.execute.harbor import HarborBackend
from benchnuke.ingest.harbor import ingest_harbor_task
from benchnuke.models import (
    CoverageLevel,
    CoverageRow,
    ProofCells,
    Requirement,
    RequirementKind,
)
from benchnuke.report import write_audit_output
from benchnuke.stage0 import check_task
from benchnuke.work import default_work_dir


class RequirementsFile(BaseModel):
    requirements: list[Requirement]


class CoverageFile(BaseModel):
    coverage: list[CoverageRow] = Field(default_factory=list)


def run_mechanical_audit(
    task_path: Path,
    *,
    artifact_dir: Path,
    countertest_path: Path,
    requirement: Requirement,
    work_dir: Path | None = None,
    backend: VerifierBackend | None = None,
    skip_sanity: bool = False,
) -> Path:
    task = ingest_harbor_task(task_path)
    backend = backend or HarborBackend()
    work = work_dir or default_work_dir(task.task_id)
    work.mkdir(parents=True, exist_ok=True)
    write_context(task, work / "context.md")
    empty = work / "empty"
    empty.mkdir(exist_ok=True)
    if not skip_sanity:
        check_task(task, backend, empty)

    runs = work / "runs"
    official_ref = (
        backend.grade(task, task.solution_dir, log_dir=runs / "grade-gold")
        if task.solution_dir
        else None
    )
    official_adv = backend.grade(task, artifact_dir, log_dir=runs / "grade-adv")
    counter_ref = (
        backend.countertest(
            task, task.solution_dir, countertest_path, log_dir=runs / "prove-gold"
        )
        if task.solution_dir
        else None
    )
    counter_adv = backend.countertest(
        task, artifact_dir, countertest_path, log_dir=runs / "prove-adv"
    )
    cells = ProofCells(
        official_reference=official_ref,
        official_adversarial=official_adv,
        countertest_reference=counter_ref,
        countertest_adversarial=counter_adv,
    )
    classification = classify_finding(requirement=requirement, cells=cells)
    output = write_audit_output(
        output_dir=work / "audit-output",
        task_id=task.task_id,
        requirement=requirement,
        cells=cells,
        notes=[
            "white-box attacker; official-boundary grade",
            (
                f"classification={classification.status.value} "
                f"evidence={classification.evidence_level.value}"
            ),
        ],
        artifact_dir=artifact_dir,
        countertest_path=countertest_path,
        log_dirs={
            "grade-gold": runs / "grade-gold",
            "grade-adv": runs / "grade-adv",
            "prove-gold": runs / "prove-gold",
            "prove-adv": runs / "prove-adv",
        },
    )
    return output


PROCESS_CATEGORIES = frozenset({"process", "workflow"})

# Legacy fallback for requirements.json files written before categories existed
# (all "functional"). Match only unambiguous workflow/doc chores; anything
# unsure stays attackable.
PROCESS_STATEMENT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bwork on a new branch\b",
        r"\bnew branch from (main|master)\b",
        r"\bcommit (everything|all (changes|work))\b",
        r"\bupdate (the )?(cli )?documentation\b",
        r"\bupdate (the )?changelog\b",
    )
)


def is_process_requirement(requirement: Requirement) -> bool:
    """True for contribution-workflow chores the verifier boundary cannot grade."""
    if requirement.category.strip().lower() in PROCESS_CATEGORIES:
        return True
    return any(
        pattern.search(requirement.statement) for pattern in PROCESS_STATEMENT_PATTERNS
    )


def attackable_requirement_ids(
    coverage: CoverageFile,
    requirements: RequirementsFile | None = None,
) -> list[str]:
    explicit: set[str] | None = None
    process: set[str] = set()
    if requirements is not None:
        explicit = {
            item.id
            for item in requirements.requirements
            if item.kind is RequirementKind.EXPLICIT
        }
        process = {
            item.id for item in requirements.requirements if is_process_requirement(item)
        }
    ids: list[str] = []
    for row in coverage.coverage:
        if row.coverage not in {CoverageLevel.NONE, CoverageLevel.PARTIAL}:
            continue
        if explicit is not None and row.requirement_id not in explicit:
            continue
        if row.requirement_id in process:
            continue
        ids.append(row.requirement_id)
    return ids


def skipped_process_requirement_ids(
    coverage: CoverageFile,
    requirements: RequirementsFile | None = None,
) -> list[str]:
    """Coverage-gapped explicit ids withheld from attack as process chores."""
    if requirements is None:
        return []
    process = {
        item.id
        for item in requirements.requirements
        if item.kind is RequirementKind.EXPLICIT and is_process_requirement(item)
    }
    return [
        row.requirement_id
        for row in coverage.coverage
        if row.coverage in {CoverageLevel.NONE, CoverageLevel.PARTIAL}
        and row.requirement_id in process
    ]


def load_requirements(path: Path) -> RequirementsFile:
    try:
        return RequirementsFile.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise SchemaError(f"invalid requirements file {path}: {exc}") from exc


def load_coverage(path: Path) -> CoverageFile:
    try:
        return CoverageFile.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise SchemaError(f"invalid coverage file {path}: {exc}") from exc
