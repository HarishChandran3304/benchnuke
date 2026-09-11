"""In-process Harbor runner for unit tests. Does not invoke pytest or Docker."""

from __future__ import annotations

from pathlib import Path

from benchnuke.execute.harbor import parse_harbor_job
from benchnuke.models import PassFail


class ScriptedHarborRunner:
    """Simulate `harbor run` by inspecting the staged task tree.

    Official tests (no tests/countertest.py): any Cache implementation passes.
    Counter-test staging (tests/countertest.py present): implementations that
    stash exceptions fail; gold does not.
    nop agent always fails.
    """

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
        del timeout
        passed = _simulate(task_path, agent)
        verifier = jobs_dir / job_name / "trial" / "verifier"
        verifier.mkdir(parents=True, exist_ok=True)
        (verifier / "reward.txt").write_text("1\n" if passed else "0\n", encoding="utf-8")
        if log_dir is not None:
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / "stdout.log").write_text(
                f"simulated harbor run agent={agent} task={task_path}\n",
                encoding="utf-8",
            )
            (log_dir / "stderr.log").write_text("", encoding="utf-8")
        return parse_harbor_job(jobs_dir)


def _simulate(task_path: Path, agent: str) -> bool:
    if agent == "nop":
        return False
    cache = task_path / "solution" / "cache.py"
    if not cache.is_file():
        return False
    source = cache.read_text(encoding="utf-8")
    tests = task_path / "tests"
    is_counter = tests.is_dir() and (tests / "countertest.py").is_file()
    if is_counter:
        return "self._store[key] = exc" not in source
    return "class Cache" in source
