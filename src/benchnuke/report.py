"""Write BAF 1.0 audit.json + report.md + proof bundle."""

from __future__ import annotations

import shutil
from pathlib import Path

from benchnuke.classify import classify_finding
from benchnuke.models import (
    AuditDocument,
    AuditSummary,
    CoverageLevel,
    CoverageRow,
    Finding,
    FindingStatus,
    ProofCells,
    Requirement,
    StageRecord,
    TaskRef,
)

NO_BYPASS_SENTENCE = "No verifier bypass was found under our attack budget for this task."


def load_audit_document(path: Path) -> AuditDocument | None:
    if not path.is_file():
        return None
    return AuditDocument.model_validate_json(path.read_text(encoding="utf-8"))


def save_audit_document(path: Path, document: AuditDocument) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(document.model_dump_json(indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def upsert_stage(
    document: AuditDocument, name: str, status: str, error: str | None = None
) -> None:
    document.current_stage = name
    for row in document.stages:
        if row.name == name:
            row.status = status
            row.error = error
            return
    document.stages.append(StageRecord(name=name, status=status, error=error))


def write_audit_output(
    *,
    output_dir: Path,
    task_id: str,
    requirement: Requirement,
    cells: ProofCells,
    notes: list[str] | None = None,
    artifact_dir: Path | None = None,
    countertest_path: Path | None = None,
    log_dirs: dict[str, Path] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    classification = classify_finding(requirement=requirement, cells=cells)
    existing = load_audit_document(output_dir / "audit.json")
    prior = list(existing.findings) if existing else []
    kept = [row for row in prior if row.requirement_id != requirement.id]
    finding_id = next(
        (row.id for row in prior if row.requirement_id == requirement.id), None
    ) or _next_finding_id(prior)
    finding_rel = Path("findings") / finding_id
    finding_dir = output_dir / finding_rel
    finding_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, str] = {}
    if artifact_dir and artifact_dir.is_dir():
        dest = finding_dir / "adversarial"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(artifact_dir, dest)
        artifacts["adversarial_solution"] = str(finding_rel / "adversarial")
    if countertest_path and countertest_path.is_file():
        dest_file = finding_dir / "countertest.py"
        shutil.copy2(countertest_path, dest_file)
        artifacts["countertest"] = str(finding_rel / "countertest.py")
    if log_dirs:
        logs_dest = finding_dir / "logs"
        logs_dest.mkdir(exist_ok=True)
        for name, src in log_dirs.items():
            if src.is_dir():
                target = logs_dest / name
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(src, target)
                artifacts[f"log_{name}"] = str(finding_rel / "logs" / name)
    finding = Finding(
        id=finding_id,
        requirement_id=requirement.id,
        status=classification.status,
        finding_class=classification.finding_class,
        severity=classification.severity,
        evidence_level=classification.evidence_level,
        official_reference=cells.official_reference,
        official_verifier=cells.official_adversarial,
        countertest_reference=cells.countertest_reference,
        countertest_adversarial=cells.countertest_adversarial,
        artifacts=artifacts,
    )
    # ProveStage reads findings[0] as the latest result, so the new finding stays first.
    findings = [finding, *kept]
    specification = list(existing.specification) if existing else []
    if not any(row.id == requirement.id for row in specification):
        specification.append(requirement)
    coverage_rows = list(existing.coverage) if existing else []
    base_summary = existing.summary if existing else AuditSummary()
    summary = recompute_summary(
        base_summary,
        specification=specification,
        coverage=coverage_rows,
        findings=findings,
    )
    merged_notes = list(dict.fromkeys([*(existing.notes if existing else []), *(notes or [])]))
    document = AuditDocument(
        task=TaskRef(id=task_id, source_format="harbor"),
        specification=specification,
        coverage=coverage_rows,
        findings=findings,
        summary=summary,
        notes=merged_notes,
        run_status="completed",
        current_stage=existing.current_stage if existing else None,
        work_dir=existing.work_dir if existing else "",
        task_path=existing.task_path if existing else "",
        stages=list(existing.stages) if existing else [],
    )
    save_audit_document(output_dir / "audit.json", document)
    (output_dir / "report.md").write_text(
        _render_report(task_id=task_id, findings=findings, requirements=specification),
        encoding="utf-8",
    )
    (finding_dir / "finding.json").write_text(
        finding.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    return output_dir


def recompute_summary(
    base: AuditSummary,
    *,
    specification: list[Requirement],
    coverage: list[CoverageRow],
    findings: list[Finding],
    attacks_attempted: int | None = None,
) -> AuditSummary:
    """Refresh summary counters from document content.

    attacks_attempted never decreases: it keeps the higher of the maintained
    count (graded attacks, per GradeStage) and the count derivable here.
    """
    attempted = attacks_attempted if attacks_attempted is not None else len(findings)
    return base.model_copy(
        update={
            "requirements_total": len(specification),
            "coverage_full": sum(
                1 for row in coverage if row.coverage is CoverageLevel.FULL
            ),
            "coverage_partial": sum(
                1 for row in coverage if row.coverage is CoverageLevel.PARTIAL
            ),
            "coverage_none": sum(
                1 for row in coverage if row.coverage is CoverageLevel.NONE
            ),
            "attacks_attempted": max(base.attacks_attempted, attempted),
            "confirmed_findings": sum(
                1 for row in findings if row.status is FindingStatus.CONFIRMED
            ),
            "probable_findings": sum(
                1 for row in findings if row.status is FindingStatus.PROBABLE
            ),
        }
    )


def write_empty_report(
    *,
    output_dir: Path,
    task_id: str,
    findings: list[Finding] | None = None,
) -> Path:
    """Report for a completed audit with no confirmed bypass. Never claims the task is clean."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.md").write_text(
        _render_empty_report(task_id=task_id, findings=findings or []),
        encoding="utf-8",
    )
    return output_dir


def _next_finding_id(findings: list[Finding]) -> str:
    used = [
        int(row.id[1:]) for row in findings if row.id.startswith("F") and row.id[1:].isdigit()
    ]
    return f"F{max(used, default=0) + 1:03d}"


def _cell(value: object) -> str:
    if value is None:
        return "n/a"
    return str(value).upper()


def _render_empty_report(*, task_id: str, findings: list[Finding]) -> str:
    lines = [
        f"# Audit Report — {task_id}",
        "",
        "## Result",
        "",
        NO_BYPASS_SENTENCE,
    ]
    if findings:
        lines += [
            "",
            "## Candidates (not confirmed)",
            "",
            "| Finding | Requirement | Status | Class |",
            "|---|---|---|---|",
        ]
        for row in findings:
            finding_class = row.finding_class.value if row.finding_class else "-"
            lines.append(
                f"| {row.id} | {row.requirement_id} | {row.status.value} | {finding_class} |"
            )
    return "\n".join(lines) + "\n"


def _render_report(
    *,
    task_id: str,
    findings: list[Finding],
    requirements: list[Requirement],
) -> str:
    by_id = {row.id: row for row in requirements}
    confirmed = [row for row in findings if row.status is FindingStatus.CONFIRMED]
    current = findings[0]
    if confirmed:
        ids = ", ".join(row.requirement_id for row in confirmed)
        headline = f"Confirmed verifier gaps: {len(confirmed)}\nRequirement: {ids}"
    elif current.status is FindingStatus.UNRESOLVED:
        headline = NO_BYPASS_SENTENCE
    else:
        headline = f"Status: {current.status.value}"
    lines = [
        f"# Audit Report — {task_id}",
        "",
        "## Result",
        "",
        headline,
    ]
    for finding in findings:
        requirement = by_id.get(finding.requirement_id)
        statement = requirement.statement if requirement else finding.requirement_id
        kind = f" ({requirement.kind.value})" if requirement else ""
        lines += [
            "",
            f"## {finding.id} — {statement}",
            "",
            f"Severity: {finding.severity.value}",
            f"Evidence level: {finding.evidence_level.value}",
            f"Requirement: {finding.requirement_id}{kind}",
            "",
            "### Evidence",
            "",
            "| Check | Reference | Adversarial |",
            "|---|---|---|",
            (
                f"| Official verifier | {_cell(finding.official_reference)} | "
                f"{_cell(finding.official_verifier)} |"
            ),
            (
                f"| Counter-test | {_cell(finding.countertest_reference)} | "
                f"{_cell(finding.countertest_adversarial)} |"
            ),
        ]
    return "\n".join(lines) + "\n"
