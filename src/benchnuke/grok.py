"""Grok harness adapter: run stages via headless `grok -p`."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from benchnuke.agent.base import AgentResult, StageSpec
from benchnuke.errors import GrokRunnerError


class GrokRunner:
    def __init__(self, binary: str | None = None) -> None:
        self.binary = (
            binary
            or os.environ.get("BENCHNUKE_GROK_BIN")
            or os.environ.get("GROK_BIN")
            or "grok"
        )

    def build_argv(self, spec: StageSpec) -> list[str]:
        argv = [
            self.binary,
            "--prompt-file",
            str(spec.prompt_file),
            "--cwd",
            str(spec.cwd.resolve()),
            "--output-format",
            "json",
            "--yolo",
            "--no-subagents",
            "--max-turns",
            str(spec.max_turns),
            "--rules",
            spec.rules,
            "--deny",
            "Bash(*benchnuke audit*)",
            "--deny",
            "Bash(*benchnuke prove*)",
        ]
        if spec.tools:
            argv.extend(["--tools", ",".join(spec.tools)])
        return argv

    def run(self, spec: StageSpec, log_dir: Path) -> AgentResult:
        log_dir.mkdir(parents=True, exist_ok=True)
        resolved = self.binary if Path(self.binary).is_file() else shutil.which(self.binary)
        if resolved is None:
            raise GrokRunnerError(
                f"grok binary not found: {self.binary}. "
                "Set BENCHNUKE_GROK_BIN or install grok on PATH."
            )
        argv = self.build_argv(spec)
        argv[0] = resolved
        env = os.environ.copy()
        env["BENCHNUKE_IN_AUDIT"] = "1"
        cwd = spec.cwd.resolve()
        cwd.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            argv,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=spec.timeout_sec,
        )
        (log_dir / "stdout.json").write_text(completed.stdout, encoding="utf-8")
        (log_dir / "stderr.log").write_text(completed.stderr, encoding="utf-8")
        (log_dir / "argv.txt").write_text("\n".join(argv) + "\n", encoding="utf-8")
        if completed.returncode != 0:
            raise GrokRunnerError(
                f"grok -p failed for stage {spec.name} (exit {completed.returncode}). "
                f"See {log_dir / 'stderr.log'}"
            )
        session_id = _session_id(completed.stdout)
        return AgentResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            session_id=session_id,
        )


def _session_id(stdout: str) -> str | None:
    import json

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict):
        value = payload.get("sessionId") or payload.get("session_id")
        return str(value) if value else None
    return None
