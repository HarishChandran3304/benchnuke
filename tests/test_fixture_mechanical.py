"""Mechanical 4-cell proof on leaky-cache via a scripted Harbor runner."""

from __future__ import annotations

from pathlib import Path

from benchnuke.classify import classify_finding
from benchnuke.execute.harbor import HarborBackend
from benchnuke.ingest.harbor import ingest_harbor_task
from benchnuke.models import (
    EvidenceLevel,
    FindingStatus,
    PassFail,
    ProofCells,
    Requirement,
    RequirementKind,
)
from benchnuke.report import write_audit_output


def test_ingest_leaky_cache(leaky_cache: Path) -> None:
    task = ingest_harbor_task(leaky_cache)
    assert "Failed requests must not be cached" in task.instruction
    assert task.has_reference_solution


def test_gold_passes_official_verifier(leaky_cache: Path, harbor_backend: HarborBackend) -> None:
    task = ingest_harbor_task(leaky_cache)
    backend = harbor_backend
    result = backend.grade(task, leaky_cache / "solution")
    assert result is PassFail.PASS


def test_empty_workspace_fails_official_verifier(
    leaky_cache: Path, tmp_path: Path, harbor_backend: HarborBackend
) -> None:
    task = ingest_harbor_task(leaky_cache)
    backend = harbor_backend
    empty = tmp_path / "empty"
    empty.mkdir()
    result = backend.grade(task, empty)
    assert result is PassFail.FAIL


def test_adversarial_passes_official_verifier(
    leaky_cache: Path, harbor_backend: HarborBackend
) -> None:
    task = ingest_harbor_task(leaky_cache)
    backend = harbor_backend
    result = backend.grade(task, leaky_cache / "attacks" / "R3")
    assert result is PassFail.PASS


def test_countertest_separates_gold_and_adversarial(
    leaky_cache: Path, harbor_backend: HarborBackend
) -> None:
    task = ingest_harbor_task(leaky_cache)
    backend = harbor_backend
    counter = leaky_cache / "attacks" / "R3" / "countertest.py"
    gold = backend.countertest(task, leaky_cache / "solution", counter)
    adv = backend.countertest(task, leaky_cache / "attacks" / "R3", counter)
    assert gold is PassFail.PASS
    assert adv is PassFail.FAIL


def test_four_cell_is_confirmed_level_a(
    leaky_cache: Path, harbor_backend: HarborBackend
) -> None:
    task = ingest_harbor_task(leaky_cache)
    backend = harbor_backend
    counter = leaky_cache / "attacks" / "R3" / "countertest.py"
    cells = ProofCells(
        official_reference=backend.grade(task, leaky_cache / "solution"),
        official_adversarial=backend.grade(task, leaky_cache / "attacks" / "R3"),
        countertest_reference=backend.countertest(task, leaky_cache / "solution", counter),
        countertest_adversarial=backend.countertest(task, leaky_cache / "attacks" / "R3", counter),
    )
    requirement = Requirement(
        id="R3",
        statement="Failed requests must not be cached.",
        kind=RequirementKind.EXPLICIT,
        category="error_behavior",
        source_file="instruction.md",
        evidence="Failed requests must not be cached.",
    )
    result = classify_finding(requirement=requirement, cells=cells)
    assert result.status is FindingStatus.CONFIRMED
    assert result.evidence_level is EvidenceLevel.A


def test_report_writes_baf_and_four_cell_markdown(leaky_cache: Path, tmp_path: Path) -> None:
    out = write_audit_output(
        output_dir=tmp_path / "audit-output",
        task_id="benchnuke/leaky-cache",
        requirement=Requirement(
            id="R3",
            statement="Failed requests must not be cached.",
            kind=RequirementKind.EXPLICIT,
            evidence="Failed requests must not be cached.",
        ),
        cells=ProofCells(
            official_reference=PassFail.PASS,
            official_adversarial=PassFail.PASS,
            countertest_reference=PassFail.PASS,
            countertest_adversarial=PassFail.FAIL,
        ),
        notes=["white-box attacker; official-boundary grade"],
    )
    audit = (out / "audit.json").read_text(encoding="utf-8")
    report = (out / "report.md").read_text(encoding="utf-8")
    assert '"status": "confirmed"' in audit
    assert "evidence_level" in audit
    assert "Official verifier" in report
    assert "PASS" in report
    assert "FAIL" in report
    assert "no bypass found" not in report.lower() or "confirmed" in report.lower()
    assert "Failed requests must not be cached" in report
