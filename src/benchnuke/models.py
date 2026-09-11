"""BAF 1.0 types and shared enums."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RequirementKind(StrEnum):
    EXPLICIT = "explicit"
    ENTAILED = "entailed"
    ASSUMED = "assumed"


class CoverageLevel(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    INDIRECT = "indirect"
    NONE = "none"
    UNKNOWN = "unknown"


class FindingStatus(StrEnum):
    CONFIRMED = "confirmed"
    PROBABLE = "probable"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"


class FindingClass(StrEnum):
    MISSING_REQUIREMENT = "missing_requirement"
    PARTIAL_REQUIREMENT = "partial_requirement"
    BOUNDARY_GAP = "boundary_gap"
    ERROR_PATH_GAP = "error_path_gap"
    STATE_GAP = "state_gap"
    REGRESSION_GAP = "regression_gap"
    SPECIFICATION_AMBIGUITY = "specification_ambiguity"
    REFERENCE_INCONSISTENCY = "reference_inconsistency"
    VERIFIER_INFRASTRUCTURE = "verifier_infrastructure"


class Severity(StrEnum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    INFORMATIONAL = "informational"


class EvidenceLevel(StrEnum):
    A = "A"
    B = "B"
    C = "C"


class PassFail(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class Requirement(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    statement: str
    kind: RequirementKind
    category: str = "functional"
    source_file: str = "instruction.md"
    evidence: str = ""


class ProofCells(BaseModel):
    """Four-cell proof table. Missing cells are None (not run)."""

    model_config = ConfigDict(frozen=True)

    official_reference: PassFail | None = None
    official_adversarial: PassFail | None = None
    countertest_reference: PassFail | None = None
    countertest_adversarial: PassFail | None = None


class Classification(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: FindingStatus
    evidence_level: EvidenceLevel
    finding_class: FindingClass | None = None
    severity: Severity = Severity.INFORMATIONAL


class CoverageRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    requirement_id: str
    coverage: CoverageLevel
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    suspected_gap: str = ""
    evidence: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    id: str
    requirement_id: str
    status: FindingStatus
    finding_class: FindingClass | None = None
    severity: Severity = Severity.INFORMATIONAL
    evidence_level: EvidenceLevel = EvidenceLevel.C
    attack_strategy: str = ""
    official_reference: PassFail | None = None
    official_verifier: PassFail | None = None
    countertest_reference: PassFail | None = None
    countertest_adversarial: PassFail | None = None
    artifacts: dict[str, str] = Field(default_factory=dict)


class AuditSummary(BaseModel):
    requirements_total: int = 0
    coverage_full: int = 0
    coverage_partial: int = 0
    coverage_none: int = 0
    attacks_attempted: int = 0
    confirmed_findings: int = 0
    probable_findings: int = 0


class TaskRef(BaseModel):
    id: str
    source_format: str = "harbor"
    benchmark: str = ""
    benchmark_version: str = ""


class StageRecord(BaseModel):
    name: str
    status: str = "pending"
    error: str | None = None


class AuditDocument(BaseModel):
    """Normative BAF 1.0 task-level manifest. Also the resume index."""

    schema_version: str = "1.0"
    task: TaskRef
    specification: list[Requirement] = Field(default_factory=list)
    coverage: list[CoverageRow] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    summary: AuditSummary = Field(default_factory=AuditSummary)
    notes: list[str] = Field(default_factory=list)
    run_status: str = "running"
    current_stage: str | None = None
    work_dir: str = ""
    task_path: str = ""
    stages: list[StageRecord] = Field(default_factory=list)
