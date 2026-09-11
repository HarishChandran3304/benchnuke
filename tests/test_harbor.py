"""Harbor CLI backend: argv, job parsing, solution staging (no Docker)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from benchnuke.errors import GradeError
from benchnuke.execute.harbor import (
    HarborBackend,
    HarborRunner,
    is_empty_implementation,
    materialize_countertest_task,
    materialize_oracle_task,
    needs_airgap,
    parse_harbor_job,
)
from benchnuke.ingest.harbor import ingest_harbor_task
from benchnuke.models import PassFail


def test_oracle_argv(tmp_path: Path) -> None:
    runner = HarborRunner(binary="harbor")
    argv = runner.build_argv(
        task_path=tmp_path / "task",
        agent="oracle",
        jobs_dir=tmp_path / "jobs",
        job_name="grade-gold",
    )
    assert argv[0] == "harbor"
    assert argv[1] == "run"
    assert "-p" in argv
    assert "-a" in argv
    assert "oracle" in argv
    assert "-o" in argv
    assert "--job-name" in argv
    assert "grade-gold" in argv
    assert "-y" in argv
    assert "-q" in argv


def _write_task(root: Path, *, airgap: bool) -> Path:
    root.mkdir()
    (root / "instruction.md").write_text("x\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    network = '\n[agent]\nnetwork_mode = "no-network"\n' if airgap else ""
    (root / "task.toml").write_text(f'[task]\nname = "t"{network}', encoding="utf-8")
    return root


def test_needs_airgap_from_task_toml(tmp_path: Path) -> None:
    root = _write_task(tmp_path / "task", airgap=True)
    task = ingest_harbor_task(root)
    assert needs_airgap(task) is True
    backend = HarborBackend(runner=HarborRunner(binary="harbor"))
    runner = backend._runner_for(task)
    assert runner.binary == "pier"


def test_airgap_swaps_custom_harbor_path_to_pier(tmp_path: Path, monkeypatch) -> None:
    """Airgap routing must not depend on the harbor binary's basename."""
    monkeypatch.delenv("BENCHNUKE_PIER_BIN", raising=False)
    task = ingest_harbor_task(_write_task(tmp_path / "task", airgap=True))
    backend = HarborBackend(runner=HarborRunner(binary="/opt/tools/harbor-v2"))
    assert backend._runner_for(task).binary == "pier"


def test_airgap_honors_pier_bin_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BENCHNUKE_PIER_BIN", "/opt/bin/pier-custom")
    task = ingest_harbor_task(_write_task(tmp_path / "task", airgap=True))
    backend = HarborBackend(runner=HarborRunner(binary="/opt/tools/harbor-v2"))
    assert backend._runner_for(task).binary == "/opt/bin/pier-custom"


def test_airgap_keeps_existing_pier_binary(tmp_path: Path, monkeypatch) -> None:
    """A runner already pointing at pier is left alone (custom path preserved)."""
    monkeypatch.setenv("BENCHNUKE_PIER_BIN", "/elsewhere/pier")
    task = ingest_harbor_task(_write_task(tmp_path / "task", airgap=True))
    backend = HarborBackend(runner=HarborRunner(binary="/opt/bin/pier"))
    assert backend._runner_for(task).binary == "/opt/bin/pier"


def test_non_airgap_keeps_custom_harbor_path(tmp_path: Path) -> None:
    task = ingest_harbor_task(_write_task(tmp_path / "task", airgap=False))
    assert needs_airgap(task) is False
    backend = HarborBackend(runner=HarborRunner(binary="/opt/tools/harbor-v2"))
    assert backend._runner_for(task).binary == "/opt/tools/harbor-v2"


def test_nop_argv(tmp_path: Path) -> None:
    argv = HarborRunner().build_argv(
        task_path=tmp_path / "task",
        agent="nop",
        jobs_dir=tmp_path / "jobs",
        job_name="grade-nop",
    )
    assert "nop" in argv


def test_parse_harbor_job_from_reward_txt(tmp_path: Path) -> None:
    verifier = tmp_path / "jobs" / "run" / "trial" / "verifier"
    verifier.mkdir(parents=True)
    (verifier / "reward.txt").write_text("1\n", encoding="utf-8")
    assert parse_harbor_job(tmp_path / "jobs") is PassFail.PASS


def test_parse_harbor_job_from_trial_result(tmp_path: Path) -> None:
    trial = tmp_path / "jobs" / "run" / "trial"
    trial.mkdir(parents=True)
    (trial / "result.json").write_text(
        json.dumps(
            {
                "task_name": "benchnuke/leaky-cache",
                "verifier_result": {"rewards": {"reward": 0}},
            }
        ),
        encoding="utf-8",
    )
    assert parse_harbor_job(tmp_path / "jobs") is PassFail.FAIL


def test_parse_harbor_job_missing(tmp_path: Path) -> None:
    with pytest.raises(GradeError, match="no Harbor verifier reward"):
        parse_harbor_job(tmp_path / "jobs")


def test_empty_implementation_detection(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    assert is_empty_implementation(empty) is True
    (empty / "notes.txt").write_text("hi", encoding="utf-8")
    assert is_empty_implementation(empty) is True
    (empty / "cache.py").write_text("class Cache: ...\n", encoding="utf-8")
    assert is_empty_implementation(empty) is False


def test_patch_only_solution_is_not_empty(tmp_path: Path) -> None:
    solution = tmp_path / "solution"
    solution.mkdir()
    (solution / "solve.sh").write_text("#!/bin/bash\ngit apply /solution/solution.patch\n")
    (solution / "solution.patch").write_text("diff --git a/x b/x\n")
    assert is_empty_implementation(solution) is False


def test_materialize_oracle_task_does_not_touch_source(
    leaky_cache: Path, tmp_path: Path
) -> None:
    dest = tmp_path / "staged"
    artifact = leaky_cache / "attacks" / "R3"
    original_tests = (leaky_cache / "tests" / "test.sh").read_text(encoding="utf-8")
    staged = materialize_oracle_task(leaky_cache, artifact, dest)
    assert staged == dest
    assert (dest / "solution" / "cache.py").read_text(encoding="utf-8") == (
        artifact / "cache.py"
    ).read_text(encoding="utf-8")
    assert (dest / "solution" / "solve.sh").is_file()
    assert not (dest / "attacks").exists()
    assert (leaky_cache / "tests" / "test.sh").read_text(encoding="utf-8") == original_tests
    solve = (dest / "solution" / "solve.sh").read_text(encoding="utf-8")
    assert "/solution/" in solve
    assert "/app/" in solve


def test_harbor_backend_missing_binary_raises(tmp_path: Path) -> None:
    """Non-airgapped tasks keep the configured binary; a missing one errors."""
    task = ingest_harbor_task(_write_task(tmp_path / "task", airgap=False))
    backend = HarborBackend(runner=HarborRunner(binary="harbor-not-installed-xyz"))
    with pytest.raises(GradeError, match="harbor"):
        backend.grade(task, tmp_path / "empty", log_dir=tmp_path / "logs")


def test_airgap_missing_pier_binary_raises(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BENCHNUKE_PIER_BIN", "pier-not-installed-xyz")
    task = ingest_harbor_task(_write_task(tmp_path / "task", airgap=True))
    backend = HarborBackend(runner=HarborRunner(binary="harbor"))
    with pytest.raises(GradeError, match="pier-not-installed-xyz"):
        backend.grade(task, tmp_path / "empty", log_dir=tmp_path / "logs")


def test_fixture_uses_harbor_paths(leaky_cache: Path) -> None:
    test_sh = (leaky_cache / "tests" / "test.sh").read_text(encoding="utf-8")
    solve = (leaky_cache / "solution" / "solve.sh").read_text(encoding="utf-8")
    assert "/logs/verifier" in test_sh
    assert "/tests" in test_sh
    assert "/app" in test_sh
    assert "pytest" not in test_sh
    assert "/solution/cache.py" in solve
    assert "/app/cache.py" in solve
    dockerfile = (leaky_cache / "environment" / "Dockerfile").read_text(encoding="utf-8")
    assert "pytest" not in dockerfile


def test_materialize_countertest_replaces_official_tests(
    leaky_cache: Path, tmp_path: Path
) -> None:
    dest = tmp_path / "staged-counter"
    staged = materialize_countertest_task(
        leaky_cache,
        leaky_cache / "attacks" / "R3",
        leaky_cache / "attacks" / "R3" / "countertest.py",
        dest,
    )
    assert (staged / "tests" / "countertest.py").is_file()
    test_sh = (staged / "tests" / "test.sh").read_text(encoding="utf-8")
    assert "/tests/countertest.py" in test_sh
    assert "/logs/verifier" in test_sh
    assert (staged / "solution" / "cache.py").is_file()


def test_materialize_countertest_keeps_verifier_dockerfile(
    leaky_cache: Path, tmp_path: Path
) -> None:
    task = tmp_path / "task"
    shutil.copytree(leaky_cache, task)
    (task / "tests" / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    dest = tmp_path / "staged"
    staged = materialize_countertest_task(
        task,
        leaky_cache / "attacks" / "R3",
        leaky_cache / "attacks" / "R3" / "countertest.py",
        dest,
    )
    assert (staged / "tests" / "Dockerfile").is_file()
    assert (staged / "tests" / "countertest.py").is_file()
    assert "countertest.py" in (staged / "tests" / "test.sh").read_text(encoding="utf-8")


def test_materialize_countertest_appends_copy_to_named_dockerfile(
    leaky_cache: Path, tmp_path: Path
) -> None:
    """DeepSWE-style Dockerfile only COPYs named files; countertest.py must
    still land in the image."""
    task = tmp_path / "task"
    shutil.copytree(leaky_cache, task)
    (task / "tests" / "Dockerfile").write_text(
        "FROM python:3.12-slim\n"
        "COPY test.sh /tests/test.sh\n"
        "COPY test.patch /tests/test.patch\n"
        "COPY grader.py /tests/grader.py\n"
        "COPY config.json /tests/config.json\n"
        "RUN chmod +x /tests/test.sh\n",
        encoding="utf-8",
    )
    dest = tmp_path / "staged"
    staged = materialize_countertest_task(
        task,
        leaky_cache / "attacks" / "R3",
        leaky_cache / "attacks" / "R3" / "countertest.py",
        dest,
    )
    df = (staged / "tests" / "Dockerfile").read_text(encoding="utf-8")
    assert (staged / "tests" / "countertest.py").is_file()
    assert "COPY countertest.py /tests/countertest.py" in df
    assert "COPY test.sh /tests/test.sh" in df
    # Source task Dockerfile is unchanged.
    src_df = (task / "tests" / "Dockerfile").read_text(encoding="utf-8")
    assert "countertest.py" not in src_df
