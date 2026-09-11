"""Classifier rules for confirmed / evidence-level A findings."""

from __future__ import annotations

import pytest

from benchnuke.classify import classify_finding
from benchnuke.models import (
    EvidenceLevel,
    FindingClass,
    FindingStatus,
    PassFail,
    ProofCells,
    Requirement,
    RequirementKind,
    Severity,
)


def _explicit(statement: str = "Failed requests must not be cached.") -> Requirement:
    return Requirement(
        id="R3",
        statement=statement,
        kind=RequirementKind.EXPLICIT,
        category="error_behavior",
        source_file="instruction.md",
        evidence=statement,
    )


def _assumed() -> Requirement:
    return Requirement(
        id="R7",
        statement="Implementation should be thread-safe.",
        kind=RequirementKind.ASSUMED,
        category="concurrency",
        source_file="instruction.md",
        evidence="",
    )


def test_perfect_four_cell_on_explicit_requirement_is_confirmed_level_a() -> None:
    result = classify_finding(
        requirement=_explicit(),
        cells=ProofCells(
            official_reference=PassFail.PASS,
            official_adversarial=PassFail.PASS,
            countertest_reference=PassFail.PASS,
            countertest_adversarial=PassFail.FAIL,
        ),
    )
    assert result.status == FindingStatus.CONFIRMED
    assert result.evidence_level == EvidenceLevel.A
    assert result.finding_class == FindingClass.MISSING_REQUIREMENT
    assert result.severity in {Severity.MAJOR, Severity.CRITICAL}


def test_no_reference_solution_cannot_reach_level_a() -> None:
    result = classify_finding(
        requirement=_explicit(),
        cells=ProofCells(
            official_reference=None,
            official_adversarial=PassFail.PASS,
            countertest_reference=None,
            countertest_adversarial=PassFail.FAIL,
        ),
    )
    assert result.status == FindingStatus.PROBABLE
    assert result.evidence_level == EvidenceLevel.B
    assert result.status != FindingStatus.CONFIRMED


def test_static_suspected_gap_only_is_unresolved_level_c() -> None:
    result = classify_finding(
        requirement=_explicit(),
        cells=ProofCells(
            official_reference=None,
            official_adversarial=None,
            countertest_reference=None,
            countertest_adversarial=None,
        ),
    )
    assert result.status == FindingStatus.UNRESOLVED
    assert result.evidence_level == EvidenceLevel.C


def test_assumed_requirement_cannot_be_confirmed() -> None:
    result = classify_finding(
        requirement=_assumed(),
        cells=ProofCells(
            official_reference=PassFail.PASS,
            official_adversarial=PassFail.PASS,
            countertest_reference=PassFail.PASS,
            countertest_adversarial=PassFail.FAIL,
        ),
    )
    assert result.status != FindingStatus.CONFIRMED
    assert result.evidence_level != EvidenceLevel.A


def test_gold_failing_official_verifier_is_not_level_a() -> None:
    result = classify_finding(
        requirement=_explicit(),
        cells=ProofCells(
            official_reference=PassFail.FAIL,
            official_adversarial=PassFail.PASS,
            countertest_reference=PassFail.PASS,
            countertest_adversarial=PassFail.FAIL,
        ),
    )
    assert result.status == FindingStatus.REJECTED
    assert result.finding_class == FindingClass.REFERENCE_INCONSISTENCY
    assert result.evidence_level != EvidenceLevel.A


def test_gold_failing_countertest_is_reference_inconsistency() -> None:
    result = classify_finding(
        requirement=_explicit(),
        cells=ProofCells(
            official_reference=PassFail.PASS,
            official_adversarial=PassFail.PASS,
            countertest_reference=PassFail.FAIL,
            countertest_adversarial=PassFail.FAIL,
        ),
    )
    assert result.status == FindingStatus.REJECTED
    assert result.finding_class == FindingClass.REFERENCE_INCONSISTENCY
    assert result.evidence_level != EvidenceLevel.A


def test_official_verifier_rejecting_adversarial_is_not_a_gap() -> None:
    result = classify_finding(
        requirement=_explicit(),
        cells=ProofCells(
            official_reference=PassFail.PASS,
            official_adversarial=PassFail.FAIL,
            countertest_reference=PassFail.PASS,
            countertest_adversarial=PassFail.FAIL,
        ),
    )
    assert result.status == FindingStatus.REJECTED
    assert result.evidence_level != EvidenceLevel.A


def test_countertest_passing_on_adversarial_is_not_a_gap() -> None:
    result = classify_finding(
        requirement=_explicit(),
        cells=ProofCells(
            official_reference=PassFail.PASS,
            official_adversarial=PassFail.PASS,
            countertest_reference=PassFail.PASS,
            countertest_adversarial=PassFail.PASS,
        ),
    )
    assert result.status == FindingStatus.REJECTED


def test_entailed_requirement_is_not_confirmed_even_with_perfect_cells() -> None:
    requirement = Requirement(
        id="R2",
        statement="Timeout of zero disables the timer.",
        kind=RequirementKind.ENTAILED,
        category="boundary",
        source_file="instruction.md",
        evidence="timeout may be disabled",
    )
    result = classify_finding(
        requirement=requirement,
        cells=ProofCells(
            official_reference=PassFail.PASS,
            official_adversarial=PassFail.PASS,
            countertest_reference=PassFail.PASS,
            countertest_adversarial=PassFail.FAIL,
        ),
    )
    assert result.status != FindingStatus.CONFIRMED
    assert result.evidence_level != EvidenceLevel.A


@pytest.mark.parametrize(
    ("kind",),
    [(RequirementKind.ASSUMED,), (RequirementKind.ENTAILED,)],
)
def test_non_explicit_kinds_never_headline_confirmed(kind: RequirementKind) -> None:
    requirement = Requirement(
        id="Rx",
        statement="something",
        kind=kind,
        category="other",
        source_file="instruction.md",
        evidence="x",
    )
    result = classify_finding(
        requirement=requirement,
        cells=ProofCells(
            official_reference=PassFail.PASS,
            official_adversarial=PassFail.PASS,
            countertest_reference=PassFail.PASS,
            countertest_adversarial=PassFail.FAIL,
        ),
    )
    assert result.status != FindingStatus.CONFIRMED
