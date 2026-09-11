"""Counter-test staging: the candidate's work must reach /app first.

DeepSWE-style tasks run the verifier in a separate container whose /app
starts pristine at the base commit; the agent's work is collected as
/logs/artifacts/model.patch. The staged test.sh must restore that work
before countertest.py runs (grader.py prepare, or a plain git apply).
The execution tests below run the generated scripts in a local sandbox
with rewritten paths — no Docker, no harbor.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from benchnuke.execute.harbor import materialize_countertest_task

_SINGLE_CONTAINER_SH = """#!/usr/bin/env bash
set -euo pipefail
mkdir -p /logs/verifier
cd /app
if PYTHONPATH=/app python /tests/countertest.py; then
  echo 1 > /logs/verifier/reward.txt
  exit 0
fi
echo 0 > /logs/verifier/reward.txt
exit 0
"""

requires_bash = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None,
    reason="generated-script execution needs bash and git on the host",
)


def _write_task(root: Path, *, grader: bool, collect: bool) -> Path:
    root.mkdir()
    (root / "instruction.md").write_text("x\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    if grader:
        (root / "tests" / "grader.py").write_text("# grader\n", encoding="utf-8")
        (root / "tests" / "config.json").write_text("{}\n", encoding="utf-8")
        (root / "tests" / "test.patch").write_text("\n", encoding="utf-8")
    collect_block = (
        "[[verifier.collect]]\n"
        'command = "cd /app && git diff --binary BASE HEAD > /logs/artifacts/model.patch"\n'
        if collect
        else ""
    )
    (root / "task.toml").write_text(
        '[task]\nname = "t"\n[verifier]\ntimeout_sec = 60.0\n' + collect_block,
        encoding="utf-8",
    )
    return root


def _stage(task: Path, tmp_path: Path) -> Path:
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    (artifact / "solution.py").write_text("x = 1\n", encoding="utf-8")
    countertest = tmp_path / "countertest.py"
    countertest.write_text("print('ok')\n", encoding="utf-8")
    return materialize_countertest_task(task, artifact, countertest, tmp_path / "staged")


def _script(staged: Path) -> str:
    return (staged / "tests" / "test.sh").read_text(encoding="utf-8")


def test_grader_task_runs_prepare_before_countertest(tmp_path: Path) -> None:
    task = _write_task(tmp_path / "task", grader=True, collect=True)
    staged = _stage(task, tmp_path)
    assert (staged / "tests" / "grader.py").is_file()
    assert (staged / "tests" / "countertest.py").is_file()
    script = _script(staged)
    assert script.index("grader.py prepare") < script.index("countertest.py")
    assert "if ! python /tests/grader.py prepare; then" in script
    assert "if PYTHONPATH=/app python /tests/countertest.py; then" in script
    assert "echo 1 > /logs/verifier/reward.txt" in script
    assert "echo 0 > /logs/verifier/reward.txt" in script


def test_grader_task_apply_failure_writes_no_reward(tmp_path: Path) -> None:
    """prepare exits 0 with reward.json when model.patch won't apply; the run
    must end without any reward so the grade is retried, not mis-scored."""
    staged = _stage(_write_task(tmp_path / "task", grader=True, collect=True), tmp_path)
    script = _script(staged)
    assert "rm -f /logs/verifier/reward.json" in script


def test_collect_task_without_grader_applies_model_patch(tmp_path: Path) -> None:
    staged = _stage(_write_task(tmp_path / "task", grader=False, collect=True), tmp_path)
    script = _script(staged)
    assert "grader.py" not in script
    assert "git apply --whitespace=nowarn /logs/artifacts/model.patch" in script
    assert script.index("model.patch") < script.index("countertest.py")
    assert "if PYTHONPATH=/app python /tests/countertest.py; then" in script


def test_single_container_task_script_is_unchanged(tmp_path: Path) -> None:
    staged = _stage(_write_task(tmp_path / "task", grader=False, collect=False), tmp_path)
    assert _script(staged) == _SINGLE_CONTAINER_SH


def test_leaky_cache_script_is_unchanged(leaky_cache: Path, tmp_path: Path) -> None:
    staged = materialize_countertest_task(
        leaky_cache,
        leaky_cache / "attacks" / "R3",
        leaky_cache / "attacks" / "R3" / "countertest.py",
        tmp_path / "staged",
    )
    assert _script(staged) == _SINGLE_CONTAINER_SH


def test_grader_task_without_collect_hook_still_prepares(tmp_path: Path) -> None:
    staged = _stage(_write_task(tmp_path / "task", grader=True, collect=False), tmp_path)
    assert "grader.py prepare" in _script(staged)


def test_missing_task_toml_keeps_single_container_script(tmp_path: Path) -> None:
    task = _write_task(tmp_path / "task", grader=False, collect=False)
    (task / "task.toml").unlink()
    staged = _stage(task, tmp_path)
    assert _script(staged) == _SINGLE_CONTAINER_SH


def test_malformed_task_toml_keeps_single_container_script(tmp_path: Path) -> None:
    task = _write_task(tmp_path / "task", grader=False, collect=False)
    (task / "task.toml").write_text("not = [valid\n", encoding="utf-8")
    staged = _stage(task, tmp_path)
    assert _script(staged) == _SINGLE_CONTAINER_SH


def test_staging_does_not_mutate_source_task(tmp_path: Path) -> None:
    task = _write_task(tmp_path / "task", grader=True, collect=True)
    tests_before = {p.name: p.read_bytes() for p in (task / "tests").iterdir()}
    toml_before = (task / "task.toml").read_bytes()
    _stage(task, tmp_path)
    assert {p.name: p.read_bytes() for p in (task / "tests").iterdir()} == tests_before
    assert (task / "task.toml").read_bytes() == toml_before


def test_grader_task_dockerfile_still_copies_countertest(tmp_path: Path) -> None:
    task = _write_task(tmp_path / "task", grader=True, collect=True)
    (task / "tests" / "Dockerfile").write_text(
        "FROM python:3.12-slim\n"
        "COPY test.sh /tests/test.sh\n"
        "COPY grader.py /tests/grader.py\n",
        encoding="utf-8",
    )
    staged = _stage(task, tmp_path)
    dockerfile = (staged / "tests" / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY grader.py /tests/grader.py" in dockerfile
    assert "COPY countertest.py /tests/countertest.py" in dockerfile


# --- generated-script execution (local sandbox, no Docker) -------------------

_CONTAINER_PATHS = {
    "/logs/verifier": ("logs", "verifier"),
    "/logs/artifacts": ("logs", "artifacts"),
    "/tests": ("tests",),
    "/app": ("app",),
}

_GRADER_STUB = """import json
import os
import pathlib
import sys

mode = os.environ["GRADER_STUB_MODE"]
if mode == "ok":
    sys.exit(0)
if mode == "apply_failed":
    out = pathlib.Path(os.environ["GRADER_STUB_VERIFIER_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    (out / "reward.json").write_text(json.dumps({"reward": 0, "apply_failed": 1}))
    sys.exit(0)
sys.exit(3)
"""

_COUNTER_PASS = "import sys\nsys.exit(0)\n"
_COUNTER_FAIL = "import sys\nsys.exit(1)\n"
_COUNTER_NEEDS_PATCH = (
    "import pathlib\n"
    "import sys\n"
    'sys.exit(0 if pathlib.Path("mod.py").read_text() == "patched\\n" else 1)\n'
)


def _sandbox_script(script: str, tmp_path: Path) -> tuple[Path, Path]:
    """Rewrite container paths into a sandbox dir; returns (run.sh, sandbox)."""
    sandbox = tmp_path / "sandbox"
    mapping = {
        token: str(sandbox.joinpath(*parts)) for token, parts in _CONTAINER_PATHS.items()
    }
    pattern = re.compile("|".join(re.escape(token) for token in mapping))
    rewritten = pattern.sub(lambda m: mapping[m.group(0)], script)
    for parts in _CONTAINER_PATHS.values():
        sandbox.joinpath(*parts).mkdir(parents=True, exist_ok=True)
    (sandbox / "home").mkdir()
    run = tmp_path / "run.sh"
    run.write_text(rewritten, encoding="utf-8")
    return run, sandbox


def _execute(
    run: Path, sandbox: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    # HOME is sandboxed so `git config --global` never touches the real one.
    full_env = {"HOME": str(sandbox / "home"), "PATH": os.environ.get("PATH", "")}
    full_env.update(env or {})
    return subprocess.run(
        ["bash", str(run)], check=False, capture_output=True, text=True, env=full_env
    )


def _reward(sandbox: Path) -> str | None:
    reward = sandbox / "logs" / "verifier" / "reward.txt"
    return reward.read_text(encoding="utf-8") if reward.is_file() else None


def _grader_env(mode: str, sandbox: Path) -> dict[str, str]:
    return {
        "GRADER_STUB_MODE": mode,
        "GRADER_STUB_VERIFIER_DIR": str(sandbox / "logs" / "verifier"),
    }


def _stage_script(tmp_path: Path, *, grader: bool, collect: bool) -> str:
    task = _write_task(tmp_path / "task", grader=grader, collect=collect)
    return _script(_stage(task, tmp_path))


def _git_repo_with_patch(app: Path, patch_path: Path) -> None:
    """Commit mod.py at 'base', then capture the diff to 'patched' as the patch."""

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=app, check=True, capture_output=True, text=True
        ).stdout

    git("init", "-q")
    (app / "mod.py").write_text("base\n", encoding="utf-8")
    git("add", "mod.py")
    git(
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.com",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-q",
        "-m",
        "base",
    )
    (app / "mod.py").write_text("patched\n", encoding="utf-8")
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(git("diff"), encoding="utf-8")
    git("checkout", "-q", "--", "mod.py")


@requires_bash
def test_grader_script_rewards_countertest_result(tmp_path: Path) -> None:
    script = _stage_script(tmp_path, grader=True, collect=True)
    run, sandbox = _sandbox_script(script, tmp_path)
    (sandbox / "tests" / "grader.py").write_text(_GRADER_STUB, encoding="utf-8")
    (sandbox / "tests" / "countertest.py").write_text(_COUNTER_PASS, encoding="utf-8")
    env = _grader_env("ok", sandbox)
    result = _execute(run, sandbox, env)
    assert result.returncode == 0, result.stderr
    assert _reward(sandbox) == "1\n"
    (sandbox / "tests" / "countertest.py").write_text(_COUNTER_FAIL, encoding="utf-8")
    result = _execute(run, sandbox, env)
    assert result.returncode == 0, result.stderr
    assert _reward(sandbox) == "0\n"


@requires_bash
def test_grader_script_apply_failure_writes_no_reward(tmp_path: Path) -> None:
    script = _stage_script(tmp_path, grader=True, collect=True)
    run, sandbox = _sandbox_script(script, tmp_path)
    (sandbox / "tests" / "grader.py").write_text(_GRADER_STUB, encoding="utf-8")
    (sandbox / "tests" / "countertest.py").write_text(_COUNTER_PASS, encoding="utf-8")
    result = _execute(run, sandbox, _grader_env("apply_failed", sandbox))
    assert result.returncode == 0, result.stderr
    assert _reward(sandbox) is None
    assert not (sandbox / "logs" / "verifier" / "reward.json").exists()


@requires_bash
def test_grader_script_prepare_crash_writes_no_reward(tmp_path: Path) -> None:
    script = _stage_script(tmp_path, grader=True, collect=True)
    run, sandbox = _sandbox_script(script, tmp_path)
    (sandbox / "tests" / "grader.py").write_text(_GRADER_STUB, encoding="utf-8")
    (sandbox / "tests" / "countertest.py").write_text(_COUNTER_PASS, encoding="utf-8")
    result = _execute(run, sandbox, _grader_env("crash", sandbox))
    assert result.returncode == 0, result.stderr
    assert _reward(sandbox) is None


@requires_bash
def test_collect_script_applies_model_patch_before_countertest(tmp_path: Path) -> None:
    script = _stage_script(tmp_path, grader=False, collect=True)
    run, sandbox = _sandbox_script(script, tmp_path)
    _git_repo_with_patch(sandbox / "app", sandbox / "logs" / "artifacts" / "model.patch")
    (sandbox / "tests" / "countertest.py").write_text(
        _COUNTER_NEEDS_PATCH, encoding="utf-8"
    )
    result = _execute(run, sandbox)
    assert result.returncode == 0, result.stderr
    # reward 1 proves countertest.py saw the patched file (else it exits 1 -> 0).
    assert _reward(sandbox) == "1\n"


@requires_bash
def test_collect_script_apply_failure_writes_no_reward(tmp_path: Path) -> None:
    script = _stage_script(tmp_path, grader=False, collect=True)
    run, sandbox = _sandbox_script(script, tmp_path)
    _git_repo_with_patch(sandbox / "app", sandbox / "logs" / "artifacts" / "model.patch")
    (sandbox / "logs" / "artifacts" / "model.patch").write_text(
        "not a patch\n", encoding="utf-8"
    )
    (sandbox / "tests" / "countertest.py").write_text(_COUNTER_PASS, encoding="utf-8")
    result = _execute(run, sandbox)
    assert result.returncode == 0, result.stderr
    assert _reward(sandbox) is None


@requires_bash
def test_collect_script_without_patch_still_runs_countertest(tmp_path: Path) -> None:
    """No model.patch (nop agent) and /app not a git repo: run as-is."""
    script = _stage_script(tmp_path, grader=False, collect=True)
    run, sandbox = _sandbox_script(script, tmp_path)
    (sandbox / "tests" / "countertest.py").write_text(_COUNTER_PASS, encoding="utf-8")
    result = _execute(run, sandbox)
    assert result.returncode == 0, result.stderr
    assert _reward(sandbox) == "1\n"


@requires_bash
def test_single_container_script_runs_countertest(tmp_path: Path) -> None:
    script = _stage_script(tmp_path, grader=False, collect=False)
    run, sandbox = _sandbox_script(script, tmp_path)
    (sandbox / "tests" / "countertest.py").write_text(_COUNTER_PASS, encoding="utf-8")
    result = _execute(run, sandbox)
    assert result.returncode == 0, result.stderr
    assert _reward(sandbox) == "1\n"
    (sandbox / "tests" / "countertest.py").write_text(_COUNTER_FAIL, encoding="utf-8")
    result = _execute(run, sandbox)
    assert result.returncode == 0, result.stderr
    assert _reward(sandbox) == "0\n"
