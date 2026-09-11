"""Select a headless coding-agent harness."""

from __future__ import annotations

import os

from benchnuke.agent.pi import PiRunner
from benchnuke.errors import AgentRunnerError
from benchnuke.grok import GrokRunner, HeadlessAgent


def select_runner(
    harness: str | None = None,
    *,
    model: str | None = None,
    provider: str | None = None,
) -> HeadlessAgent:
    name = (harness or os.environ.get("BENCHNUKE_HARNESS") or "pi").strip().lower()
    provider = (provider or os.environ.get("BENCHNUKE_PROVIDER") or "openrouter").strip()
    model = (model or os.environ.get("BENCHNUKE_MODEL") or "").strip()
    if name in {"pi", "pi-agent"}:
        if not model:
            raise AgentRunnerError(
                "Pi harness requires --model (OpenRouter id), e.g. "
                "--model anthropic/claude-sonnet-4"
            )
        return PiRunner(provider=provider, model=model)
    if name == "grok":
        return GrokRunner()
    raise AgentRunnerError(f"unknown harness {name!r}; use pi or grok")
