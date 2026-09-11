"""Deterministic finding classification from the 4-cell proof table."""

from __future__ import annotations

from benchnuke.models import (
    Classification,
    EvidenceLevel,
    FindingClass,
    FindingStatus,
    PassFail,
    ProofCells,
    Requirement,
    RequirementKind,
    Severity,
)


def classify_finding(*, requirement: Requirement, cells: ProofCells) -> Classification:
    """Map proof cells to status + evidence level.

    Confirmed / evidence A requires an explicit requirement and:
    official(adversarial)=PASS, countertest(adversarial)=FAIL,
    countertest(reference)=PASS.
    """
    if _is_static_only(cells):
        return Classification(
            status=FindingStatus.UNRESOLVED,
            evidence_level=EvidenceLevel.C,
            finding_class=None,
            severity=Severity.INFORMATIONAL,
        )

    if cells.official_reference == PassFail.FAIL:
        return Classification(
            status=FindingStatus.REJECTED,
            evidence_level=EvidenceLevel.C,
            finding_class=FindingClass.REFERENCE_INCONSISTENCY,
            severity=Severity.MAJOR,
        )

    if cells.official_adversarial == PassFail.FAIL:
        return Classification(
            status=FindingStatus.REJECTED,
            evidence_level=EvidenceLevel.C,
            finding_class=None,
            severity=Severity.INFORMATIONAL,
        )

    if cells.countertest_adversarial == PassFail.PASS:
        return Classification(
            status=FindingStatus.REJECTED,
            evidence_level=EvidenceLevel.C,
            finding_class=None,
            severity=Severity.INFORMATIONAL,
        )

    if (
        cells.official_adversarial == PassFail.PASS
        and cells.countertest_adversarial == PassFail.FAIL
        and cells.countertest_reference == PassFail.FAIL
    ):
        return Classification(
            status=FindingStatus.REJECTED,
            evidence_level=EvidenceLevel.C,
            finding_class=FindingClass.REFERENCE_INCONSISTENCY,
            severity=Severity.MAJOR,
        )

    gap = (
        cells.official_adversarial == PassFail.PASS
        and cells.countertest_adversarial == PassFail.FAIL
    )
    if not gap:
        return Classification(
            status=FindingStatus.UNRESOLVED,
            evidence_level=EvidenceLevel.C,
            finding_class=None,
            severity=Severity.INFORMATIONAL,
        )

    if (
        cells.countertest_reference == PassFail.PASS
        and cells.official_reference == PassFail.PASS
    ):
        return _level_a_or_weaker(requirement)
    if cells.countertest_reference == PassFail.PASS and cells.official_reference is None:
        return _level_b_or_weaker(requirement)

    return _level_b_or_weaker(requirement)


def _is_static_only(cells: ProofCells) -> bool:
    return (
        cells.official_adversarial is None
        and cells.countertest_adversarial is None
        and cells.countertest_reference is None
    )


def _level_a_or_weaker(requirement: Requirement) -> Classification:
    if requirement.kind == RequirementKind.EXPLICIT:
        return Classification(
            status=FindingStatus.CONFIRMED,
            evidence_level=EvidenceLevel.A,
            finding_class=FindingClass.MISSING_REQUIREMENT,
            severity=Severity.MAJOR,
        )
    if requirement.kind == RequirementKind.ENTAILED:
        return Classification(
            status=FindingStatus.PROBABLE,
            evidence_level=EvidenceLevel.B,
            finding_class=FindingClass.MISSING_REQUIREMENT,
            severity=Severity.MINOR,
        )
    return Classification(
        status=FindingStatus.UNRESOLVED,
        evidence_level=EvidenceLevel.C,
        finding_class=FindingClass.MISSING_REQUIREMENT,
        severity=Severity.INFORMATIONAL,
    )


def _level_b_or_weaker(requirement: Requirement) -> Classification:
    if requirement.kind == RequirementKind.EXPLICIT:
        return Classification(
            status=FindingStatus.PROBABLE,
            evidence_level=EvidenceLevel.B,
            finding_class=FindingClass.MISSING_REQUIREMENT,
            severity=Severity.MAJOR,
        )
    return Classification(
        status=FindingStatus.UNRESOLVED,
        evidence_level=EvidenceLevel.C,
        finding_class=FindingClass.MISSING_REQUIREMENT,
        severity=Severity.INFORMATIONAL,
    )
