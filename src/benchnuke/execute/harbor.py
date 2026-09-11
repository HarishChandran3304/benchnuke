"""Official Harbor CLI backend: `harbor run -a oracle|nop`."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import tomllib
import uuid
from pathlib import Path

from benchnuke.errors import GradeError
from benchnuke.execute.reward import parse_reward
from benchnuke.ingest.harbor import AuditTask
from benchnuke.models import PassFail

_IGNORE_NAMES = {
    "attacks",
    "work",
    "audits",
    "jobs",
    ".git",
    "__pycache__",
    ".pytest_cache",
    "audit-output",
    "results",
}


class HarborRunner:
    def __init__(self, binary: str | None = None) -> None:
        self.binary = (
            binary
            or os.environ.get("BENCHNUKE_HARBOR_BIN")
            or "harbor"
        )

    def resolved_binary(self) -> str:
        if Path(self.binary).is_file():
            return self.binary
        found = shutil.which(self.binary)
        if found is None:
            raise GradeError(
                f"harbor binary not found: {self.binary}. "
                "Install with `uv tool install harbor` and set BENCHNUKE_HARBOR_BIN "
                "if needed.",
                retryable=False,
            )
        return found

    def build_argv(
        self,
        *,
        task_path: Path,
        agent: str,
        jobs_dir: Path,
        job_name: str,
    ) -> list[str]:
        return [
            self.binary,
            "run",
            "-p",
            str(task_path),
            "-a",
            agent,
            "-o",
            str(jobs_dir),
            "--job-name",
            job_name,
            "-y",
            "-q",
            "-n",
            "1",
        ]

    def run(
        self,
        *,
        task_path: Path,
        agent: str,
        jobs_dir: Path,
        job_name: str,
        timeout: float,
        log_dir: Path | None,
    ) -> PassFail:
        jobs_dir.mkdir(parents=True, exist_ok=True)
        argv = self.build_argv(
            task_path=task_path,
            agent=agent,
            jobs_dir=jobs_dir,
            job_name=job_name,
        )
        argv[0] = self.resolved_binary()
        try:
            completed = subprocess.run(
                argv,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise GradeError(
                f"harbor run timed out after {timeout:.0f}s", retryable=True
            ) from exc
        if log_dir is not None:
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / "stdout.log").write_text(completed.stdout or "", encoding="utf-8")
            (log_dir / "stderr.log").write_text(completed.stderr or "", encoding="utf-8")
            (log_dir / "argv.txt").write_text("\n".join(argv) + "\n", encoding="utf-8")
            (log_dir / "returncode.txt").write_text(
                str(completed.returncode), encoding="utf-8"
            )
        if completed.returncode != 0:
            raise GradeError(
                f"harbor run failed (exit {completed.returncode}). "
                f"{(completed.stderr or completed.stdout)[-2000:]}",
                retryable=True,
            )
        outcome = parse_harbor_job(jobs_dir)
        if log_dir is not None:
            _copy_verifier_tree(jobs_dir, log_dir)
        return outcome


class HarborBackend:
    """Official cells: `harbor run` or `pier run` (DeepSWE no-network)."""

    def __init__(self, runner: HarborRunner | None = None) -> None:
        self.runner = runner or HarborRunner()

    def _runner_for(self, task: AuditTask) -> HarborRunner:
        if not isinstance(self.runner, HarborRunner):
            return self.runner  # type: ignore[return-value]
        if needs_airgap(task) and Path(self.runner.binary).name != "pier":
            return HarborRunner(
                binary=os.environ.get("BENCHNUKE_PIER_BIN") or "pier"
            )
        return self.runner

    def grade(
        self,
        task: AuditTask,
        artifact_dir: Path,
        log_dir: Path | None = None,
    ) -> PassFail:
        timeout = _harbor_timeout(task)
        owned: Path | None = None
        if log_dir is None:
            owned = Path(tempfile.mkdtemp(prefix="benchnuke-hjobs-"))
            jobs_dir = owned / "harbor-jobs"
        else:
            jobs_dir = log_dir / "harbor-jobs"
        try:
            return self._grade_with_jobs(
                task, artifact_dir, log_dir, jobs_dir, timeout
            )
        finally:
            if owned is not None:
                shutil.rmtree(owned, ignore_errors=True)

    def _grade_with_jobs(
        self,
        task: AuditTask,
        artifact_dir: Path,
        log_dir: Path | None,
        jobs_dir: Path,
        timeout: float,
    ) -> PassFail:
        runner = self._runner_for(task)
        if is_empty_implementation(artifact_dir):
            return runner.run(
                task_path=task.root,
                agent="nop",
                jobs_dir=jobs_dir,
                job_name=_job_name("nop"),
                timeout=timeout,
                log_dir=log_dir,
            )
        if task.solution_dir and artifact_dir.resolve() == task.solution_dir.resolve():
            return runner.run(
                task_path=task.root,
                agent="oracle",
                jobs_dir=jobs_dir,
                job_name=_job_name("oracle-gold"),
                timeout=timeout,
                log_dir=log_dir,
            )
        staging_root = jobs_dir.parent / "staged-task"
        if staging_root.exists():
            shutil.rmtree(staging_root)
        staged = materialize_oracle_task(task.root, artifact_dir, staging_root)
        return runner.run(
            task_path=staged,
            agent="oracle",
            jobs_dir=jobs_dir,
            job_name=_job_name("oracle-adv"),
            timeout=timeout,
            log_dir=log_dir,
        )

    def countertest(
        self,
        task: AuditTask,
        artifact_dir: Path,
        countertest_path: Path,
        log_dir: Path | None = None,
    ) -> PassFail:
        timeout = _harbor_timeout(task)
        owned: Path | None = None
        if log_dir is None:
            owned = Path(tempfile.mkdtemp(prefix="benchnuke-hprove-"))
            jobs_dir = owned / "harbor-jobs"
            staging_root = owned / "staged-task"
        else:
            jobs_dir = log_dir / "harbor-jobs"
            staging_root = log_dir / "staged-countertest"
        try:
            if staging_root.exists():
                shutil.rmtree(staging_root)
            staged = materialize_countertest_task(
                task.root, artifact_dir, countertest_path, staging_root
            )
            return self._runner_for(task).run(
                task_path=staged,
                agent="oracle",
                jobs_dir=jobs_dir,
                job_name=_job_name("oracle-counter"),
                timeout=timeout,
                log_dir=log_dir,
            )
        finally:
            if owned is not None:
                shutil.rmtree(owned, ignore_errors=True)


def needs_airgap(task: AuditTask) -> bool:
    """DeepSWE-style tasks set network_mode=no-network; Harbor Docker cannot run them."""
    for key in ("agent", "verifier", "environment"):
        block = task.task_toml.get(key)
        if isinstance(block, dict) and block.get("network_mode") == "no-network":
            return True
    verifier = task.task_toml.get("verifier")
    if isinstance(verifier, dict):
        env = verifier.get("environment")
        if isinstance(env, dict) and env.get("network_mode") == "no-network":
            return True
    return False


_IMPL_SUFFIXES = {".py", ".patch", ".diff", ".sh", ".rs", ".go", ".ts", ".js"}


def is_empty_implementation(artifact_dir: Path) -> bool:
    """True only when there is nothing for Harbor oracle to apply."""
    if not artifact_dir.is_dir():
        return True
    for path in artifact_dir.iterdir():
        if not path.is_file():
            continue
        if path.name == "countertest.py" or path.name.startswith("test_"):
            continue
        if path.suffix in _IMPL_SUFFIXES or path.name in {"solve.sh", "solve.bat"}:
            return False
    return True


def materialize_oracle_task(task_root: Path, artifact_dir: Path, dest: Path) -> Path:
    """Copy a Harbor task and swap solution/ for the candidate. Never mutates source."""

    def _ignore(directory: str, names: list[str]) -> set[str]:
        del directory
        return {name for name in names if name in _IGNORE_NAMES}

    shutil.copytree(task_root, dest, ignore=_ignore)
    solution = dest / "solution"
    if solution.exists():
        shutil.rmtree(solution)
    solution.mkdir(parents=True)
    for path in artifact_dir.iterdir():
        if not path.is_file():
            continue
        if path.name == "countertest.py" or path.name.startswith("test_"):
            continue
        shutil.copy2(path, solution / path.name)
    solve = solution / "solve.sh"
    if not solve.is_file():
        solve.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "for f in /solution/*.py; do\n"
            '  [ -f "$f" ] || continue\n'
            '  base=$(basename "$f")\n'
            '  case "$base" in test_*|countertest.py) continue ;; esac\n'
            '  cp "$f" "/app/$base"\n'
            "done\n",
            encoding="utf-8",
        )
    solve.chmod(solve.stat().st_mode | 0o111)
    return dest


_COUNTER_TEST_SH = """#!/usr/bin/env bash
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

_COUNTER_TEST_SH_GRADER = """#!/usr/bin/env bash
set -euo pipefail
mkdir -p /logs/verifier
cd /app
if ! python /tests/grader.py prepare; then
  exit 0
fi
if [ -f /logs/verifier/reward.json ]; then
  rm -f /logs/verifier/reward.json
  exit 0
fi
if PYTHONPATH=/app python /tests/countertest.py; then
  echo 1 > /logs/verifier/reward.txt
  exit 0
fi
echo 0 > /logs/verifier/reward.txt
exit 0
"""

_COUNTER_TEST_SH_MODEL_PATCH = """#!/usr/bin/env bash
set -euo pipefail
mkdir -p /logs/verifier
cd /app
git config --global --add safe.directory /app 2>/dev/null || true
if [ -s /logs/artifacts/model.patch ] && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git apply --whitespace=nowarn /logs/artifacts/model.patch || exit 0
fi
if PYTHONPATH=/app python /tests/countertest.py; then
  echo 1 > /logs/verifier/reward.txt
  exit 0
fi
echo 0 > /logs/verifier/reward.txt
exit 0
"""


def materialize_countertest_task(
    task_root: Path,
    artifact_dir: Path,
    countertest_path: Path,
    dest: Path,
) -> Path:
    """Harbor task whose verifier is the counter-test, solution is the candidate.

    The counter-test must see the candidate's work in /app. DeepSWE-style tasks
    run the verifier in a separate container whose /app starts pristine at the
    base commit; the agent's work arrives as /logs/artifacts/model.patch. The
    generated test.sh restores it before countertest.py runs: via
    `grader.py prepare` when the task ships a grader (official semantics,
    test.patch included), else via a plain `git apply` when a collect hook
    emits model.patch. Single-container tasks keep the plain script. A
    prepare/apply failure writes no reward, so the grade surfaces as a
    retryable GradeError instead of a bogus counter-test verdict.
    """
    staged = materialize_oracle_task(task_root, artifact_dir, dest)
    tests = staged / "tests"
    keep: dict[str, bytes] = {}
    if tests.exists():
        for path in tests.iterdir():
            if path.is_file() and path.name != "test.sh":
                keep[path.name] = path.read_bytes()
        shutil.rmtree(tests)
    tests.mkdir()
    for name, data in keep.items():
        (tests / name).write_bytes(data)
    shutil.copy2(countertest_path, tests / "countertest.py")
    if (tests / "grader.py").is_file():
        script = _COUNTER_TEST_SH_GRADER
    elif _collects_model_patch(staged):
        script = _COUNTER_TEST_SH_MODEL_PATCH
    else:
        script = _COUNTER_TEST_SH
    test_sh = tests / "test.sh"
    test_sh.write_text(script, encoding="utf-8")
    test_sh.chmod(test_sh.stat().st_mode | 0o111)
    _ensure_dockerfile_copies_countertest(tests / "Dockerfile")
    return staged


def _collects_model_patch(task_root: Path) -> bool:
    """True when a [[verifier.collect]] hook leaves the agent's work as model.patch."""
    toml_path = task_root / "task.toml"
    if not toml_path.is_file():
        return False
    try:
        parsed = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return False
    verifier = parsed.get("verifier")
    if not isinstance(verifier, dict):
        return False
    collect = verifier.get("collect")
    if not isinstance(collect, list):
        return False
    return any(
        isinstance(hook, dict) and "model.patch" in str(hook.get("command", ""))
        for hook in collect
    )


_DOCKERFILE_COPY_COUNTERTEST = "COPY countertest.py /tests/countertest.py"


def _ensure_dockerfile_copies_countertest(dockerfile: Path) -> None:
    """Named-file COPY lists in DeepSWE verifier images omit extra scripts.

    Append an explicit COPY so the counter-test exists at /tests/countertest.py
    inside the separate verifier container.
    """
    if not dockerfile.is_file():
        return
    text = dockerfile.read_text(encoding="utf-8")
    if "countertest.py" in text:
        return
    if not text.endswith("\n"):
        text += "\n"
    dockerfile.write_text(text + _DOCKERFILE_COPY_COUNTERTEST + "\n", encoding="utf-8")


def parse_harbor_job(jobs_dir: Path) -> PassFail:
    if not jobs_dir.exists():
        raise GradeError(f"no Harbor verifier reward under {jobs_dir}", retryable=True)
    reward_files = sorted(jobs_dir.rglob("reward.txt"), key=lambda p: p.stat().st_mtime)
    if reward_files:
        return parse_reward(reward_files[-1].parent)
    json_rewards = sorted(jobs_dir.rglob("reward.json"), key=lambda p: p.stat().st_mtime)
    if json_rewards:
        return parse_reward(json_rewards[-1].parent)
    for result_path in sorted(
        jobs_dir.rglob("result.json"), key=lambda p: p.stat().st_mtime, reverse=True
    ):
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        parsed = _reward_from_result_payload(payload)
        if parsed is not None:
            return parsed
    raise GradeError(f"no Harbor verifier reward under {jobs_dir}", retryable=True)


def _reward_from_result_payload(payload: object) -> PassFail | None:
    if not isinstance(payload, dict):
        return None
    verifier = payload.get("verifier_result")
    if isinstance(verifier, dict):
        rewards = verifier.get("rewards")
        if isinstance(rewards, dict) and "reward" in rewards:
            value = float(rewards["reward"])
            return PassFail.PASS if value >= 1.0 else PassFail.FAIL
    trials = payload.get("trial_results")
    if isinstance(trials, list):
        for trial in reversed(trials):
            parsed = _reward_from_result_payload(trial)
            if parsed is not None:
                return parsed
    return None


def _copy_verifier_tree(jobs_dir: Path, log_dir: Path) -> None:
    for verifier in jobs_dir.rglob("verifier"):
        if verifier.is_dir():
            target = log_dir / "verifier"
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(verifier, target)
            return


def _job_name(prefix: str) -> str:
    return f"benchnuke-{prefix}-{uuid.uuid4().hex[:8]}"


def _harbor_timeout(task: AuditTask) -> float:
    verifier = task.task_toml.get("verifier", {})
    agent = task.task_toml.get("agent", {})
    environment = task.task_toml.get("environment", {})
    verifier_t = (
        float(verifier.get("timeout_sec", 600) or 600)
        if isinstance(verifier, dict)
        else 600.0
    )
    agent_t = (
        float(agent.get("timeout_sec", 120) or 120)
        if isinstance(agent, dict)
        else 120.0
    )
    build_t = (
        float(environment.get("build_timeout_sec", 180) or 180)
        if isinstance(environment, dict)
        else 180.0
    )
    return verifier_t + agent_t + build_t + 60.0
