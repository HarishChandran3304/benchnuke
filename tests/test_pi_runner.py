from __future__ import annotations

from pathlib import Path

import benchnuke.agent.pi as pi_module
from benchnuke.agent.base import StageSpec
from benchnuke.agent.factory import select_runner
from benchnuke.agent.pi import PiRunner, map_tools
from benchnuke.errors import AgentRunnerError
from benchnuke.grok import GrokRunner


def test_map_tools_grok_names_to_pi() -> None:
    assert map_tools(("read_file", "list_dir", "search_replace", "run_terminal_cmd")) == (
        "read",
        "ls",
        "edit",
        "bash",
    )


def test_pi_argv_openrouter(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("extract requirements", encoding="utf-8")
    runner = PiRunner(binary="pi", provider="openrouter", model="anthropic/claude-sonnet-4")
    argv = runner.build_argv(
        StageSpec(
            name="spec-extract",
            prompt_file=prompt,
            cwd=tmp_path,
            max_turns=20,
            tools=("read_file", "grep", "list_dir", "search_replace"),
            rules="Do not invoke benchnuke audit.",
        )
    )
    assert argv[0] == "pi"
    assert "-p" in argv
    assert "--mode" in argv
    assert "json" in argv
    assert "--provider" in argv
    assert "openrouter" in argv
    assert "--model" in argv
    assert "anthropic/claude-sonnet-4" in argv
    assert "--tools" in argv
    tools = argv[argv.index("--tools") + 1]
    assert "read" in tools
    assert "ls" in tools
    assert "edit" in tools
    assert "bash" not in tools
    assert "--no-session" in argv
    assert "--no-context-files" in argv
    assert "--append-system-prompt" in argv
    assert f"@{prompt.resolve()}" in argv
    assert "--cwd" not in argv  # Pi uses process cwd
    assert "--max-turns" not in argv  # Pi has no turn-limit flag
    assert "--thinking" not in argv  # unset: pi default thinking level


def test_pi_argv_thinking_flag(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("map coverage", encoding="utf-8")
    runner = PiRunner(binary="pi", provider="openrouter", model="z-ai/glm-5.3-flash")
    argv = runner.build_argv(
        StageSpec(
            name="coverage",
            prompt_file=prompt,
            cwd=tmp_path,
            max_turns=20,
            tools=(),
            rules="Do not invoke benchnuke audit.",
            thinking="high",
        )
    )
    assert argv[argv.index("--thinking") + 1] == "high"


def test_pi_strips_openrouter_prefix() -> None:
    runner = PiRunner(
        binary="pi",
        provider="openrouter",
        model="openrouter/openai/gpt-5",
    )
    assert runner.provider == "openrouter"
    assert runner.model == "openai/gpt-5"


def test_select_runner_defaults_to_pi() -> None:
    runner = select_runner("pi", model="openai/gpt-4o")
    assert isinstance(runner, PiRunner)
    assert runner.provider == "openrouter"
    assert runner.model == "openai/gpt-4o"


def test_select_runner_pi_requires_model(monkeypatch) -> None:
    monkeypatch.delenv("BENCHNUKE_MODEL", raising=False)
    try:
        select_runner("pi")
        raised = False
    except AgentRunnerError:
        raised = True
    assert raised


def test_select_runner_grok() -> None:
    runner = select_runner("grok")
    assert isinstance(runner, GrokRunner)


def test_pi_missing_binary_raises(tmp_path: Path, monkeypatch) -> None:
    prompt = tmp_path / "p.md"
    prompt.write_text("x", encoding="utf-8")
    monkeypatch.setenv("PATH", str(tmp_path))
    runner = PiRunner(binary="pi-not-installed", provider="openrouter", model="x")
    try:
        runner.run(
            StageSpec(
                name="spec-extract",
                prompt_file=prompt,
                cwd=tmp_path,
                max_turns=1,
                tools=("read_file",),
                rules="none",
            ),
            log_dir=tmp_path / "logs",
        )
        raised = False
    except AgentRunnerError:
        raised = True
    assert raised


def _fake_pi(tmp_path: Path) -> str:
    fake = tmp_path / "pi-fake"
    fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake.chmod(0o755)
    return str(fake)


def _stage_spec(tmp_path: Path, max_turns: int = 400) -> StageSpec:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("x", encoding="utf-8")
    return StageSpec(
        name="attack",
        prompt_file=prompt,
        cwd=tmp_path,
        max_turns=max_turns,
        tools=("read_file",),
        rules="none",
    )


def test_pi_warns_max_turns_unenforced_once_per_process(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(pi_module, "_warned_max_turns", False)
    runner = PiRunner(binary=_fake_pi(tmp_path), provider="openrouter", model="x")
    spec = _stage_spec(tmp_path)
    runner.run(spec, tmp_path / "logs1")
    runner.run(spec, tmp_path / "logs2")
    err = capsys.readouterr().err
    assert err.count("max_turns=400 is unenforced") == 1
    assert "wall-clock timeout" in err


def test_pi_stage_log_notes_unenforced_max_turns(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(pi_module, "_warned_max_turns", False)
    runner = PiRunner(binary=_fake_pi(tmp_path), provider="openrouter", model="x")
    spec = _stage_spec(tmp_path, max_turns=200)
    runner.run(spec, tmp_path / "logs1")
    runner.run(spec, tmp_path / "logs2")
    capsys.readouterr()
    # Every stage log carries the note even though stderr warns only once.
    for name in ("logs1", "logs2"):
        note = (tmp_path / name / "stderr.log").read_text(encoding="utf-8")
        assert "max_turns=200 is unenforced" in note
        assert "wall-clock timeout" in note
