"""Process requirements are filtered out of the attack list."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchnuke.agent.base import AgentResult, StageSpec
from benchnuke.execute.harbor import HarborBackend
from benchnuke.models import CoverageLevel, CoverageRow, Requirement, RequirementKind
from benchnuke.pipeline import (
    CoverageFile,
    RequirementsFile,
    attackable_requirement_ids,
    skipped_process_requirement_ids,
)
from benchnuke.stages.pipeline import run_audit

_BROKEN_CACHE = '"""Attack that does not implement Cache."""\n\n\ndef cache():\n    return None\n'


def _requirement(
    req_id: str,
    statement: str = "Cache successful responses.",
    *,
    kind: RequirementKind = RequirementKind.EXPLICIT,
    category: str = "functional",
) -> Requirement:
    return Requirement(
        id=req_id,
        statement=statement,
        kind=kind,
        category=category,
        evidence=statement,
    )


def _coverage(req_id: str, level: CoverageLevel = CoverageLevel.NONE) -> CoverageRow:
    return CoverageRow(requirement_id=req_id, coverage=level, confidence=0.9)


def _files(
    requirements: list[Requirement], rows: list[CoverageRow]
) -> tuple[RequirementsFile, CoverageFile]:
    return RequirementsFile(requirements=requirements), CoverageFile(coverage=rows)


def test_functional_gap_stays_attackable() -> None:
    requirements, coverage = _files([_requirement("R1")], [_coverage("R1")])
    assert attackable_requirement_ids(coverage, requirements) == ["R1"]


@pytest.mark.parametrize(
    "level", [CoverageLevel.FULL, CoverageLevel.INDIRECT, CoverageLevel.UNKNOWN]
)
def test_covered_requirements_not_attackable(level: CoverageLevel) -> None:
    requirements, coverage = _files([_requirement("R1")], [_coverage("R1", level)])
    assert attackable_requirement_ids(coverage, requirements) == []


@pytest.mark.parametrize("category", ["process", "workflow", "Process", " WORKFLOW "])
def test_process_category_excluded(category: str) -> None:
    requirements, coverage = _files(
        [_requirement("R1", "Entries expire after 60 seconds.", category=category)],
        [_coverage("R1")],
    )
    assert attackable_requirement_ids(coverage, requirements) == []


@pytest.mark.parametrize(
    "statement",
    [
        "IMPORTANT: Please work on a new branch from main and commit everything "
        "when you are done.",
        "Work on a new branch before making changes.",
        "Create a new branch from master.",
        "Commit everything when you are done.",
        "COMMIT EVERYTHING WHEN DONE.",
        "Commit all changes to your branch.",
        "Commit all work before finishing.",
        "Update the CLI documentation.",
        "Update documentation for the new flag.",
        "Update the changelog.",
        "Update CHANGELOG.",
    ],
)
def test_legacy_workflow_keywords_excluded(statement: str) -> None:
    requirements, coverage = _files([_requirement("R1", statement)], [_coverage("R1")])
    assert attackable_requirement_ids(coverage, requirements) == []


@pytest.mark.parametrize(
    "statement",
    [
        "Cache must validate integrity on load and discard corrupted entries.",
        "Update the CLI to reject invalid input.",
        "The parser must handle branch instructions.",
        "Failed requests must not be cached.",
        "The CLI must document all exit codes in --help output.",
        "Commit retries when the backend is unreachable.",
    ],
)
def test_functional_statements_not_filtered(statement: str) -> None:
    requirements, coverage = _files([_requirement("R1", statement)], [_coverage("R1")])
    assert attackable_requirement_ids(coverage, requirements) == ["R1"]


def test_skipped_ids_report_only_filtered_process() -> None:
    requirements, coverage = _files(
        [
            _requirement("R1"),
            _requirement("R2", "Commit everything when you are done."),
            _requirement("R3", "Update the changelog."),
            _requirement(
                "R4", "Commit everything.", kind=RequirementKind.ENTAILED
            ),
        ],
        [
            _coverage("R1"),
            _coverage("R2"),
            _coverage("R3", CoverageLevel.FULL),
            _coverage("R4"),
        ],
    )
    assert attackable_requirement_ids(coverage, requirements) == ["R1"]
    assert skipped_process_requirement_ids(coverage, requirements) == ["R2"]


def test_no_requirements_file_keeps_coverage_only_contract() -> None:
    coverage = CoverageFile(
        coverage=[_coverage("R1"), _coverage("R2", CoverageLevel.PARTIAL)]
    )
    assert attackable_requirement_ids(coverage) == ["R1", "R2"]
    assert skipped_process_requirement_ids(coverage) == []


class ScriptedRunner:
    """One legacy-keyword chore (R1), one categorized chore (R2), one real gap (R3)."""

    def __init__(self) -> None:
        self.stages: list[str] = []

    def run(self, spec: StageSpec, log_dir: Path) -> AgentResult:
        self.stages.append(spec.name)
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "stdout.json").write_text("{}", encoding="utf-8")
        work = spec.cwd
        if spec.name == "spec-extract":
            rows = [
                {
                    "id": "R1",
                    "statement": "IMPORTANT: Please work on a new branch from main "
                    "and commit everything when you are done.",
                    "kind": "explicit",
                    "category": "functional",
                    "source_file": "instruction.md",
                    "evidence": "work on a new branch from main and commit everything",
                },
                {
                    "id": "R2",
                    "statement": "Update the CLI documentation.",
                    "kind": "explicit",
                    "category": "process",
                    "source_file": "instruction.md",
                    "evidence": "Update the CLI documentation.",
                },
                {
                    "id": "R3",
                    "statement": "Failed requests must not be cached.",
                    "kind": "explicit",
                    "category": "error_behavior",
                    "source_file": "instruction.md",
                    "evidence": "Failed requests must not be cached.",
                },
            ]
            payload = json.dumps({"requirements": rows})
            (work / "requirements.json").write_text(payload, encoding="utf-8")
        elif spec.name == "coverage":
            rows = [
                {
                    "requirement_id": req_id,
                    "coverage": level,
                    "confidence": 0.9,
                    "suspected_gap": "",
                    "evidence": [],
                }
                for req_id, level in (
                    ("R1", "none"),
                    ("R2", "partial"),
                    ("R3", "none"),
                )
            ]
            payload = json.dumps({"coverage": rows})
            (work / "coverage.json").write_text(payload, encoding="utf-8")
        elif spec.name.startswith("attack-"):
            req_id = spec.name.removeprefix("attack-")
            dest = work / "artifacts" / req_id
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "cache.py").write_text(_BROKEN_CACHE, encoding="utf-8")
        return AgentResult(returncode=0, stdout="{}", stderr="", session_id="test")


def test_run_audit_skips_process_requirements(
    leaky_cache: Path,
    tmp_path: Path,
    harbor_backend: HarborBackend,
    capsys: pytest.CaptureFixture[str],
) -> None:
    work = tmp_path / "work"
    runner = ScriptedRunner()
    run_audit(leaky_cache, work_dir=work, runner=runner, backend=harbor_backend)
    assert "attack-R3" in runner.stages
    assert "attack-R1" not in runner.stages
    assert "attack-R2" not in runner.stages
    out = capsys.readouterr().out
    assert "R1" in out and "R2" in out
    payload = json.loads((work / "audit-output" / "audit.json").read_text(encoding="utf-8"))
    notes = " ".join(payload["notes"])
    assert "R1" in notes and "R2" in notes and "process" in notes
