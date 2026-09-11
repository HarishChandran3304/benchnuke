"""Pi coding-agent harness (https://pi.dev) with OpenRouter models."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from benchnuke.agent.base import AgentResult, StageSpec
from benchnuke.errors import AgentRunnerError

_TOOL_MAP = {
    "read_file": "read",
    "list_dir": "ls",
    "search_replace": "edit",
    "run_terminal_cmd": "bash",
    "write": "write",
    "grep": "grep",
}


def map_tools(names: tuple[str, ...]) -> tuple[str, ...]:
    mapped: list[str] = []
    seen: set[str] = set()
    for name in names:
        dest = _TOOL_MAP.get(name, name)
        if dest not in seen:
            seen.add(dest)
            mapped.append(dest)
    return tuple(mapped)


def normalize_model(provider: str, model: str) -> tuple[str, str]:
    prefix = f"{provider}/"
    if model.startswith(prefix):
        model = model[len(prefix) :]
    return provider, model


# `pi --help` exposes no turn-limit flag, so StageSpec.max_turns cannot be
# enforced under this harness. Warn loudly instead of dropping it silently.
_warned_max_turns = False


def _max_turns_warning(spec: StageSpec) -> str:
    return (
        f"pi has no turn-limit flag: max_turns={spec.max_turns} is unenforced "
        f"for stage {spec.name!r}; wall-clock timeout ({spec.timeout_sec}s) "
        "is the only budget backstop."
    )


def _warn_max_turns_unenforced(spec: StageSpec) -> None:
    global _warned_max_turns
    if _warned_max_turns:
        return
    _warned_max_turns = True
    print(f"benchnuke: warning: {_max_turns_warning(spec)}", file=sys.stderr)


class PiRunner:
    """Headless `pi -p` against OpenRouter (or any Pi provider).

    Pi has no turn-limit flag, so StageSpec.max_turns is unenforced: run()
    warns once per process on stderr and notes it in each stage's stderr.log.
    """

    def __init__(
        self,
        *,
        binary: str | None = None,
        provider: str = "openrouter",
        model: str,
        api_key: str | None = None,
    ) -> None:
        self.binary = binary or os.environ.get("BENCHNUKE_PI_BIN") or "pi"
        self.provider, self.model = normalize_model(provider, model)
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")

    def build_argv(self, spec: StageSpec) -> list[str]:
        prompt = spec.prompt_file.resolve()
        tools = map_tools(spec.tools)
        argv = [
            self.binary,
            "-p",
            "--mode",
            "json",
            "--provider",
            self.provider,
            "--model",
            self.model,
            "--no-session",
            "--no-context-files",
            "--append-system-prompt",
            spec.rules,
        ]
        if tools:
            argv.extend(["--tools", ",".join(tools)])
        argv.extend(["--", f"@{prompt}"])
        return argv

    def run(self, spec: StageSpec, log_dir: Path) -> AgentResult:
        log_dir.mkdir(parents=True, exist_ok=True)
        cwd = spec.cwd.resolve()
        cwd.mkdir(parents=True, exist_ok=True)
        resolved = self.binary if Path(self.binary).is_file() else shutil.which(self.binary)
        if resolved is None:
            raise AgentRunnerError(
                f"pi binary not found: {self.binary}. "
                "Install with `npm install -g --ignore-scripts @earendil-works/pi-coding-agent` "
                "or set BENCHNUKE_PI_BIN."
            )
        argv = self.build_argv(spec)
        argv[0] = resolved
        _warn_max_turns_unenforced(spec)
        env = os.environ.copy()
        env["BENCHNUKE_IN_AUDIT"] = "1"
        if self.api_key:
            env["OPENROUTER_API_KEY"] = self.api_key
        stdout_path = log_dir / "stdout.log"
        stderr_path = log_dir / "stderr.log"
        (log_dir / "argv.txt").write_text("\n".join(argv) + "\n", encoding="utf-8")
        with stdout_path.open("w", encoding="utf-8") as out, stderr_path.open(
            "w", encoding="utf-8"
        ) as err:
            err.write(f"benchnuke: note: {_max_turns_warning(spec)}\n")
            err.flush()
            try:
                proc = subprocess.Popen(
                    argv,
                    cwd=cwd,
                    stdout=out,
                    stderr=err,
                    text=True,
                    env=env,
                )
                returncode = proc.wait(timeout=spec.timeout_sec)
            except subprocess.TimeoutExpired as exc:
                proc.kill()
                proc.wait()
                err.write(f"\ntimed out after {spec.timeout_sec}s\n")
                err.flush()
                raise AgentRunnerError(
                    f"pi -p timed out for stage {spec.name} after {spec.timeout_sec}s"
                ) from exc
        stdout_text = stdout_path.read_text(encoding="utf-8")
        stderr_text = stderr_path.read_text(encoding="utf-8")
        if returncode != 0:
            raise AgentRunnerError(
                f"pi -p failed for stage {spec.name} (exit {returncode}). "
                f"See {stderr_path}"
            )
        return AgentResult(
            returncode=returncode,
            stdout=stdout_text,
            stderr=stderr_text,
            session_id=None,
        )
