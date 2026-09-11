"""Harness-neutral abstractions for headless coding-agent runners."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

DEFAULT_STAGE_TIMEOUT_SEC = 60 * 60


@dataclass(frozen=True)
class StageSpec:
    name: str
    prompt_file: Path
    cwd: Path
    max_turns: int
    tools: tuple[str, ...]
    rules: str
    timeout_sec: int = DEFAULT_STAGE_TIMEOUT_SEC
    #: pi --thinking level (off|minimal|low|medium|high|xhigh|max); None = pi default
    thinking: str | None = None


@dataclass(frozen=True)
class AgentResult:
    returncode: int
    stdout: str
    stderr: str
    session_id: str | None


class HeadlessAgent(Protocol):
    def run(self, spec: StageSpec, log_dir: Path) -> AgentResult: ...
