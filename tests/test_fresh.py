"""--fresh clears the run directory before starting over."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchnuke.agent.base import AgentResult
from benchnuke.errors import TaskIngestError
from benchnuke.grok_audit import run_grok_audit
from benchnuke.stages.pipeline import _clear_work_dir


def _make_run_dir(root: Path) -> None:
    (root / "artifacts" / "R6").mkdir(parents=True)
    (root / "artifacts" / "R6" / "official.json").write_text("{}", encoding="utf-8")
    (root / "results").mkdir(parents=True)
    (root / "STALE.txt").write_text("old state", encoding="utf-8")


def test_clear_work_dir_removes_run_contents(tmp_path: Path) -> None:
    root = tmp_path / "run"
    _make_run_dir(root)
    _clear_work_dir(root)
    assert not root.exists()


def test_clear_work_dir_tolerates_missing_and_empty(tmp_path: Path) -> None:
    _clear_work_dir(tmp_path / "nonexistent")
    empty = tmp_path / "empty"
    empty.mkdir()
    _clear_work_dir(empty)
    assert not empty.exists()


def test_clear_work_dir_refuses_non_run_directory(tmp_path: Path) -> None:
    root = tmp_path / "documents"
    root.mkdir()
    (root / "taxes.pdf").write_text("do not delete", encoding="utf-8")
    with pytest.raises(TaskIngestError, match="not a benchnuke run directory"):
        _clear_work_dir(root)
    assert (root / "taxes.pdf").is_file()


class _Scripted:
    """Minimal one-requirement pipeline script (attack passes official, gets proved)."""

    def __init__(self, leaky_cache: Path) -> None:
        self.leaky_cache = leaky_cache

    def run(self, spec, log_dir: Path) -> AgentResult:
        log_dir.mkdir(parents=True, exist_ok=True)
        work = spec.cwd
        if spec.name == "spec-extract":
            (work / "requirements.json").write_text(
                json.dumps(
                    {
                        "requirements": [
                            {
                                "id": "R1",
                                "statement": "Failed requests must not be cached.",
                                "kind": "explicit",
                                "category": "functional",
                                "source_file": "instruction.md",
                                "evidence": "Failed requests must not be cached.",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
        elif spec.name == "coverage":
            (work / "coverage.json").write_text(
                json.dumps({"coverage": [{"requirement_id": "R1", "coverage": "none"}]}),
                encoding="utf-8",
            )
        elif spec.name.startswith("attack-"):
            dest = work / "artifacts" / spec.name.removeprefix("attack-")
            dest.mkdir(parents=True, exist_ok=True)
            src = self.leaky_cache / "attacks" / "R3" / "cache.py"
            (dest / "cache.py").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        elif spec.name.startswith("countertest-"):
            dest = work / "artifacts" / spec.name.removeprefix("countertest-")
            src = self.leaky_cache / "attacks" / "R3" / "countertest.py"
            (dest / "countertest.py").write_text(
                src.read_text(encoding="utf-8"), encoding="utf-8"
            )
        return AgentResult(returncode=0, stdout="{}", stderr="", session_id=None)


def test_fresh_run_clears_stale_files(
    leaky_cache: Path, tmp_path: Path, harbor_backend
) -> None:
    work = tmp_path / "run"
    runner = _Scripted(leaky_cache)
    run_grok_audit(leaky_cache, work_dir=work, runner=runner, backend=harbor_backend)
    stale = work / "STALE.txt"
    stale.write_text("previous run", encoding="utf-8")
    assert stale.is_file()
    run_grok_audit(
        leaky_cache, work_dir=work, runner=runner, backend=harbor_backend, fresh=True
    )
    assert not stale.exists()
