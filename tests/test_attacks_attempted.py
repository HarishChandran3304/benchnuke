"""attacks_attempted counts every requirement that received an official grade."""

from __future__ import annotations

import json
from pathlib import Path

from benchnuke.agent.base import AgentResult, StageSpec
from benchnuke.execute.harbor import HarborBackend
from benchnuke.grok_audit import run_grok_audit
from benchnuke.ingest.harbor import ingest_harbor_task
from benchnuke.models import (
    AuditDocument,
    AuditSummary,
    PassFail,
    ProofCells,
    Requirement,
    RequirementKind,
    TaskRef,
)
from benchnuke.pipeline import run_mechanical_audit
from benchnuke.report import load_audit_document, save_audit_document, write_audit_output
from benchnuke.stages.base import AuditContext
from benchnuke.stages.grade import GradeStage
from benchnuke.stages.layout import WorkLayout

_BROKEN_CACHE = '"""Attack that does not implement Cache."""\n\n\ndef cache():\n    return None\n'


def _requirement(req_id: str) -> Requirement:
    return Requirement(
        id=req_id,
        statement=f"Requirement {req_id} must hold.",
        kind=RequirementKind.EXPLICIT,
        evidence=f"Requirement {req_id} must hold.",
    )


def _stashing_cache(leaky_cache: Path) -> str:
    return (leaky_cache / "attacks" / "R3" / "cache.py").read_text(encoding="utf-8")


def test_graded_count_counts_dirs_with_official_json(tmp_path: Path) -> None:
    work = WorkLayout(tmp_path)
    assert work.graded_count() == 0
    for req_id, result in (("R1", "fail"), ("R2", "pass")):
        path = work.official_grade(req_id)
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"result": result}) + "\n", encoding="utf-8")
    work.artifact("R3").mkdir(parents=True)
    assert work.graded_count() == 2


def test_grade_stage_recomputes_count_never_increments(
    leaky_cache: Path, tmp_path: Path, harbor_backend: HarborBackend
) -> None:
    task = ingest_harbor_task(leaky_cache)
    work = WorkLayout(tmp_path / "work")
    work.root.mkdir(parents=True)
    ctx = AuditContext(
        task=task,
        work=work,
        backend=harbor_backend,
        runner=ScriptedGrok(leaky_cache, {}),
        document=AuditDocument(
            task=TaskRef(id=task.task_id, source_format="harbor"),
            work_dir=str(work.root),
            task_path=str(leaky_cache),
        ),
    )
    artifact = work.artifact("R1")
    artifact.mkdir(parents=True)
    (artifact / "cache.py").write_text(_BROKEN_CACHE, encoding="utf-8")
    stage = GradeStage(_requirement("R1"))
    stage.run(ctx)
    assert ctx.document.summary.attacks_attempted == 1
    stage.run(ctx)
    assert ctx.document.summary.attacks_attempted == 1
    disk = load_audit_document(work.audit_json)
    assert disk is not None
    assert disk.summary.attacks_attempted == 1
    artifact2 = work.artifact("R2")
    artifact2.mkdir(parents=True)
    (artifact2 / "cache.py").write_text(_stashing_cache(leaky_cache), encoding="utf-8")
    GradeStage(_requirement("R2")).run(ctx)
    assert ctx.document.summary.attacks_attempted == 2


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


def test_graded_but_failed_attack_counts_toward_budget(
    leaky_cache: Path, tmp_path: Path, harbor_backend: HarborBackend
) -> None:
    work = tmp_path / "work"
    attacks = {"R1": _BROKEN_CACHE, "R2": _stashing_cache(leaky_cache)}
    output = run_grok_audit(
        leaky_cache,
        work_dir=work,
        runner=ScriptedGrok(leaky_cache, attacks),
        backend=harbor_backend,
    )
    grade = json.loads((work / "artifacts" / "R1" / "official.json").read_text(encoding="utf-8"))
    assert grade["result"] == "fail"
    payload = json.loads((output / "audit.json").read_text(encoding="utf-8"))
    assert [row["requirement_id"] for row in payload["findings"]] == ["R2"]
    assert payload["findings"][0]["status"] == "confirmed"
    assert payload["summary"]["attacks_attempted"] == 2
    stage_names = [row["name"] for row in payload["stages"]]
    assert "grade-R1" in stage_names
    assert "prove-R1" not in stage_names


def test_resume_preserves_attempted_count(
    leaky_cache: Path, tmp_path: Path, harbor_backend: HarborBackend
) -> None:
    work = tmp_path / "work"
    attacks = {"R1": _BROKEN_CACHE, "R2": _stashing_cache(leaky_cache)}
    grok = ScriptedGrok(leaky_cache, attacks)
    run_grok_audit(leaky_cache, work_dir=work, runner=grok, backend=harbor_backend)
    grok.stages.clear()
    output = run_grok_audit(leaky_cache, work_dir=work, runner=grok, backend=harbor_backend)
    assert grok.stages == []
    payload = json.loads((output / "audit.json").read_text(encoding="utf-8"))
    assert payload["summary"]["attacks_attempted"] == 2
    assert [row["requirement_id"] for row in payload["findings"]] == ["R2"]


def test_write_audit_output_keeps_higher_attempted_count(tmp_path: Path) -> None:
    out = tmp_path / "audit-output"
    save_audit_document(
        out / "audit.json",
        AuditDocument(
            task=TaskRef(id="bench/task", source_format="harbor"),
            summary=AuditSummary(attacks_attempted=3),
        ),
    )
    write_audit_output(
        output_dir=out,
        task_id="bench/task",
        requirement=_requirement("R2"),
        cells=ProofCells(
            official_reference=PassFail.PASS,
            official_adversarial=PassFail.PASS,
            countertest_reference=PassFail.PASS,
            countertest_adversarial=PassFail.FAIL,
        ),
    )
    document = load_audit_document(out / "audit.json")
    assert document is not None
    assert len(document.findings) == 1
    assert document.summary.attacks_attempted == 3


def test_mechanical_path_counts_one_attempt(
    leaky_cache: Path, tmp_path: Path, harbor_backend: HarborBackend
) -> None:
    work = tmp_path / "work"
    run_mechanical_audit(
        leaky_cache,
        artifact_dir=leaky_cache / "attacks" / "R3",
        countertest_path=leaky_cache / "attacks" / "R3" / "countertest.py",
        requirement=Requirement(
            id="R3",
            statement="Failed requests must not be cached.",
            kind=RequirementKind.EXPLICIT,
            evidence="Failed requests must not be cached.",
        ),
        work_dir=work,
        backend=harbor_backend,
    )
    payload = json.loads((work / "audit-output" / "audit.json").read_text(encoding="utf-8"))
    assert len(payload["findings"]) == 1
    assert payload["summary"]["attacks_attempted"] == 1
