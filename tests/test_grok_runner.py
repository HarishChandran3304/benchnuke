from __future__ import annotations

from pathlib import Path

from benchnuke.grok import GrokRunner, StageSpec


def test_build_argv_includes_headless_flags(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("hello", encoding="utf-8")
    runner = GrokRunner(binary="grok")
    argv = runner.build_argv(
        spec=StageSpec(
            name="spec-extract",
            prompt_file=prompt,
            cwd=tmp_path,
            max_turns=20,
            tools=("read_file", "grep", "list_dir", "write"),
            rules="Do not invoke benchnuke audit.",
        )
    )
    assert argv[0] == "grok"
    assert "--prompt-file" in argv
    assert "--output-format" in argv
    assert "json" in argv
    assert "--yolo" in argv
    assert "--no-subagents" in argv
    assert "--max-turns" in argv
    assert "20" in argv
    assert "--cwd" in argv
    assert "--rules" in argv
    assert any("benchnuke audit" in part for part in argv)
    assert "--tools" in argv
    assert "read_file,grep,list_dir,write" in argv
    assert "--deny" in argv
    assert "Bash(*benchnuke audit*)" in argv
    # prompt text is not inlined
    assert "hello" not in argv


def test_missing_binary_raises(tmp_path: Path, monkeypatch) -> None:
    from benchnuke.errors import GrokRunnerError

    runner = GrokRunner(binary="grok-that-does-not-exist-xyz")
    prompt = tmp_path / "p.md"
    prompt.write_text("x", encoding="utf-8")
    monkeypatch.setenv("PATH", str(tmp_path))
    try:
        runner.run(
            spec=StageSpec(
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
    except GrokRunnerError:
        raised = True
    assert raised
