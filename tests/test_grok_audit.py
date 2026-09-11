from __future__ import annotations

import json
from pathlib import Path

from benchnuke.agent.base import AgentResult, StageSpec
from benchnuke.execute.harbor import HarborBackend
from benchnuke.grok_audit import run_grok_audit
from benchnuke.models import CoverageLevel


class ScriptedGrok:
    def __init__(self, leaky_cache: Path) -> None:
        self.leaky_cache = leaky_cache
        self.stages: list[str] = []

    def run(self, spec: StageSpec, log_dir: Path) -> AgentResult:
        self.stages.append(spec.name)
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "stdout.json").write_text("{}", encoding="utf-8")
        work = spec.cwd
        if spec.name == "spec-extract":
            (work / "requirements.json").write_text(
                json.dumps(
                    {
                        "requirements": [
                            {
                                "id": "R1",
                                "statement": "Cache successful responses.",
                                "kind": "explicit",
                                "category": "functional",
                                "source_file": "instruction.md",
                                "evidence": "Cache successful responses.",
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
                    }
                ),
                encoding="utf-8",
            )
        elif spec.name == "coverage":
            (work / "coverage.json").write_text(
                json.dumps(
                    {
                        "coverage": [
                            {
                                "requirement_id": "R1",
                                "coverage": CoverageLevel.FULL.value,
                                "confidence": 0.99,
                                "suspected_gap": "",
                                "evidence": ["test_caches_successful_responses"],
                            },
                            {
                                "requirement_id": "R3",
                                "coverage": CoverageLevel.NONE.value,
                                "confidence": 0.95,
                                "suspected_gap": "no failure-path assertion",
                                "evidence": [],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
        elif spec.name.startswith("attack-"):
            dest = work / "artifacts" / "R3"
            dest.mkdir(parents=True, exist_ok=True)
            src = self.leaky_cache / "attacks" / "R3" / "cache.py"
            (dest / "cache.py").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        elif spec.name.startswith("countertest-"):
            dest = work / "artifacts" / "R3"
            src = self.leaky_cache / "attacks" / "R3" / "countertest.py"
            (dest / "countertest.py").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        return AgentResult(returncode=0, stdout="{}", stderr="", session_id="test")


def test_scripted_grok_audit_confirms_r3(
    leaky_cache: Path, tmp_path: Path, harbor_backend: HarborBackend
) -> None:
    output = run_grok_audit(
        leaky_cache,
        work_dir=tmp_path / "work",
        runner=ScriptedGrok(leaky_cache),
        backend=harbor_backend,
    )
    payload = json.loads((output / "audit.json").read_text(encoding="utf-8"))
    assert payload["findings"][0]["status"] == "confirmed"
    assert payload["findings"][0]["evidence_level"] == "A"
    assert any(row["name"] == "prove-R3" for row in payload.get("stages", []))


def test_resume_skips_spec_and_coverage(
    leaky_cache: Path, tmp_path: Path, harbor_backend: HarborBackend
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    (work / "requirements.json").write_text(
        json.dumps(
            {
                "requirements": [
                    {
                        "id": "R3",
                        "statement": "Failed requests must not be cached.",
                        "kind": "explicit",
                        "category": "error_behavior",
                        "source_file": "instruction.md",
                        "evidence": "Failed requests must not be cached.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (work / "coverage.json").write_text(
        json.dumps(
            {
                "coverage": [
                    {
                        "requirement_id": "R3",
                        "coverage": CoverageLevel.NONE.value,
                        "confidence": 0.9,
                        "suspected_gap": "",
                        "evidence": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    grok = ScriptedGrok(leaky_cache)
    run_grok_audit(
        leaky_cache,
        work_dir=work,
        runner=grok,
        backend=harbor_backend,
    )
    assert "spec-extract" not in grok.stages
    assert "coverage" not in grok.stages
    assert any(name.startswith("attack-") for name in grok.stages)
