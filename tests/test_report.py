"""Report layer: finding id allocation, accumulation, and the no-bypass report stage."""

from __future__ import annotations

import json
from pathlib import Path

from benchnuke.agent.base import AgentResult, StageSpec
from benchnuke.execute.harbor import HarborBackend
from benchnuke.grok_audit import run_grok_audit
from benchnuke.models import (
    FindingStatus,
    PassFail,
    ProofCells,
    Requirement,
    RequirementKind,
)
from benchnuke.report import load_audit_document, write_audit_output

_BROKEN_CACHE = '"""Attack that does not implement Cache."""\n\n\ndef cache():\n    return None\n'
_BENIGN_CACHE = (
    '"""Honest cache: passes the official verifier and the counter-test."""\n\n\n'
    "class Cache:\n    def get(self, key):\n        return None\n"
)
_NO_BYPASS = "No verifier bypass was found under our attack budget for this task."


def _requirement(req_id: str) -> Requirement:
    return Requirement(
        id=req_id,
        statement=f"Requirement {req_id} must hold.",
        kind=RequirementKind.EXPLICIT,
        evidence=f"Requirement {req_id} must hold.",
    )


def test_finding_ids_increment_and_prior_findings_survive(tmp_path: Path) -> None:
    out = tmp_path / "audit-output"
    write_audit_output(
        output_dir=out,
        task_id="bench/task",
        requirement=_requirement("R13"),
        cells=ProofCells(
            official_reference=PassFail.PASS,
            official_adversarial=PassFail.PASS,
            countertest_reference=PassFail.FAIL,
            countertest_adversarial=PassFail.FAIL,
        ),
    )
    write_audit_output(
        output_dir=out,
        task_id="bench/task",
        requirement=_requirement("R19"),
        cells=ProofCells(
            official_reference=PassFail.PASS,
            official_adversarial=PassFail.PASS,
            countertest_reference=PassFail.PASS,
            countertest_adversarial=PassFail.FAIL,
        ),
    )
    document = load_audit_document(out / "audit.json")
    assert document is not None
    assert [row.id for row in document.findings] == ["F002", "F001"]
    assert document.findings[0].status is FindingStatus.CONFIRMED
    assert document.findings[0].requirement_id == "R19"
    assert document.findings[1].status is FindingStatus.REJECTED
    assert document.findings[1].requirement_id == "R13"
    assert document.summary.confirmed_findings == 1
    assert document.summary.attacks_attempted == 2
    report = (out / "report.md").read_text(encoding="utf-8")
    assert "Confirmed verifier gaps: 1" in report
    assert "F001" in report
    assert "F002" in report


def test_reprove_same_requirement_reuses_finding_id(tmp_path: Path) -> None:
    out = tmp_path / "audit-output"
    write_audit_output(
        output_dir=out,
        task_id="bench/task",
        requirement=_requirement("R3"),
        cells=ProofCells(official_adversarial=PassFail.FAIL),
    )
    write_audit_output(
        output_dir=out,
        task_id="bench/task",
        requirement=_requirement("R3"),
        cells=ProofCells(
            official_reference=PassFail.PASS,
            official_adversarial=PassFail.PASS,
            countertest_reference=PassFail.PASS,
            countertest_adversarial=PassFail.FAIL,
        ),
    )
    document = load_audit_document(out / "audit.json")
    assert document is not None
    assert [row.id for row in document.findings] == ["F001"]
    assert document.findings[0].status is FindingStatus.CONFIRMED
    assert (out / "findings" / "F001" / "finding.json").is_file()
    assert not (out / "findings" / "F002").exists()


class ScriptedGrok:
    """Spec/coverage cover `attacks`; attack-<id> drops the mapped cache.py source."""

    def __init__(self, leaky_cache: Path, attacks: dict[str, str]) -> None:
        self.leaky_cache = leaky_cache
        self.attacks = attacks
        self.stages: list[str] = []

    def run(self, spec: StageSpec, log_dir: Path) -> AgentResult:
        self.stages.append(spec.name)
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "stdout.json").write_text("{}", encoding="utf-8")
        work = spec.cwd
        if spec.name == "spec-extract":
            rows = [
                {
                    "id": req_id,
                    "statement": f"Requirement {req_id} must hold.",
                    "kind": "explicit",
                    "category": "functional",
                    "source_file": "instruction.md",
                    "evidence": f"Requirement {req_id} must hold.",
                }
                for req_id in self.attacks
            ]
            payload = json.dumps({"requirements": rows})
            (work / "requirements.json").write_text(payload, encoding="utf-8")
        elif spec.name == "coverage":
            rows = [
                {
                    "requirement_id": req_id,
                    "coverage": "none",
                    "confidence": 0.9,
                    "suspected_gap": "",
                    "evidence": [],
                }
                for req_id in self.attacks
            ]
            payload = json.dumps({"coverage": rows})
            (work / "coverage.json").write_text(payload, encoding="utf-8")
        elif spec.name.startswith("attack-"):
            req_id = spec.name.removeprefix("attack-")
            dest = work / "artifacts" / req_id
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "cache.py").write_text(self.attacks[req_id], encoding="utf-8")
        elif spec.name.startswith("countertest-"):
            req_id = spec.name.removeprefix("countertest-")
            dest = work / "artifacts" / req_id
            src = self.leaky_cache / "attacks" / "R3" / "countertest.py"
            (dest / "countertest.py").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        return AgentResult(returncode=0, stdout="{}", stderr="", session_id="test")


def test_report_stage_emits_no_bypass_report(
    leaky_cache: Path, tmp_path: Path, harbor_backend: HarborBackend
) -> None:
    work = tmp_path / "work"
    output = run_grok_audit(
        leaky_cache,
        work_dir=work,
        runner=ScriptedGrok(leaky_cache, {"R3": _BROKEN_CACHE}),
        backend=harbor_backend,
    )
    report = (output / "report.md").read_text(encoding="utf-8")
    assert _NO_BYPASS in report
    payload = json.loads((output / "audit.json").read_text(encoding="utf-8"))
    assert payload["run_status"] == "completed"
    assert payload["findings"] == []
    assert _NO_BYPASS in payload["notes"]
    assert {"name": "report", "status": "ok", "error": None} in payload["stages"]


def test_report_stage_skipped_on_resume(
    leaky_cache: Path, tmp_path: Path, harbor_backend: HarborBackend
) -> None:
    work = tmp_path / "work"
    grok = ScriptedGrok(leaky_cache, {"R3": _BROKEN_CACHE})
    output = run_grok_audit(leaky_cache, work_dir=work, runner=grok, backend=harbor_backend)
    first = (output / "report.md").read_text(encoding="utf-8")
    grok.stages.clear()
    run_grok_audit(leaky_cache, work_dir=work, runner=grok, backend=harbor_backend)
    assert grok.stages == []
    assert (output / "report.md").read_text(encoding="utf-8") == first
    payload = json.loads((output / "audit.json").read_text(encoding="utf-8"))
    rows = [row for row in payload["stages"] if row["name"] == "report"]
    assert rows[-1]["status"] == "skip"


def test_audit_accumulates_rejected_then_confirmed_findings(
    leaky_cache: Path, tmp_path: Path, harbor_backend: HarborBackend
) -> None:
    stashing = (leaky_cache / "attacks" / "R3" / "cache.py").read_text(encoding="utf-8")
    work = tmp_path / "work"
    output = run_grok_audit(
        leaky_cache,
        work_dir=work,
        runner=ScriptedGrok(leaky_cache, {"R1": _BENIGN_CACHE, "R2": stashing}),
        backend=harbor_backend,
    )
    payload = json.loads((output / "audit.json").read_text(encoding="utf-8"))
    assert [row["id"] for row in payload["findings"]] == ["F002", "F001"]
    assert payload["findings"][0]["status"] == "confirmed"
    assert payload["findings"][0]["requirement_id"] == "R2"
    assert payload["findings"][1]["status"] == "rejected"
    assert payload["findings"][1]["requirement_id"] == "R1"
    assert payload["summary"]["confirmed_findings"] == 1
    assert payload["summary"]["attacks_attempted"] == 2
    report = (output / "report.md").read_text(encoding="utf-8")
    assert "Confirmed verifier gaps: 1" in report
    prove_rows = [row["name"] for row in payload["stages"] if row["name"].startswith("prove-")]
    assert prove_rows == ["prove-R1", "prove-R2"]
