from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from benchnuke.cli import app

runner = CliRunner()


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "audit" in result.stdout


def test_ingest_leaky_cache(leaky_cache: Path) -> None:
    result = runner.invoke(app, ["ingest", str(leaky_cache)])
    assert result.exit_code == 0
    assert "leaky-cache" in result.stdout


def test_mechanical_audit_cli(
    leaky_cache: Path, tmp_path: Path, patch_cli_harbor: None
) -> None:
    result = runner.invoke(
        app,
        [
            "audit",
            str(leaky_cache),
            "--no-grok",
            "--artifact",
            str(leaky_cache / "attacks" / "R3"),
            "--countertest",
            str(leaky_cache / "attacks" / "R3" / "countertest.py"),
            "--requirement-id",
            "R3",
            "--statement",
            "Failed requests must not be cached.",
            "--work-dir",
            str(tmp_path / "run"),
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    audit_path = Path(result.stdout.strip())
    assert audit_path.is_file()
    payload = audit_path.read_text(encoding="utf-8")
    assert '"status": "confirmed"' in payload
    report = (audit_path.parent / "report.md").read_text(encoding="utf-8")
    assert "Official verifier" in report
    finding_dir = audit_path.parent / "findings" / "F001"
    assert (finding_dir / "adversarial" / "cache.py").is_file()
    assert (finding_dir / "countertest.py").is_file()
    assert (finding_dir / "logs" / "grade-adv" / "stdout.log").is_file()


def test_nested_audit_refused(leaky_cache: Path, monkeypatch) -> None:
    monkeypatch.setenv("BENCHNUKE_IN_AUDIT", "1")
    result = runner.invoke(app, ["audit", str(leaky_cache)])
    assert result.exit_code != 0
    assert "nested" in (result.stdout + result.stderr).lower()


def test_mechanical_requires_requirement_options(
    leaky_cache: Path, tmp_path: Path
) -> None:
    result = runner.invoke(
        app,
        [
            "audit",
            str(leaky_cache),
            "--no-grok",
            "--artifact",
            str(leaky_cache / "attacks" / "R3"),
            "--countertest",
            str(leaky_cache / "attacks" / "R3" / "countertest.py"),
            "--work-dir",
            str(tmp_path / "run"),
        ],
    )
    assert result.exit_code != 0
    assert "--requirement-id" in (result.stdout + result.stderr)


def test_mechanical_statement_must_be_in_instruction(
    leaky_cache: Path, tmp_path: Path
) -> None:
    result = runner.invoke(
        app,
        [
            "audit",
            str(leaky_cache),
            "--no-grok",
            "--artifact",
            str(leaky_cache / "attacks" / "R3"),
            "--countertest",
            str(leaky_cache / "attacks" / "R3" / "countertest.py"),
            "--requirement-id",
            "R3",
            "--statement",
            "must be thread-safe in a way the prompt never said",
            "--work-dir",
            str(tmp_path / "run"),
        ],
    )
    assert result.exit_code != 0
