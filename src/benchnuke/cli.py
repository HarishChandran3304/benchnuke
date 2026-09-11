"""benchnuke CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path

import typer

from benchnuke import __version__
from benchnuke.context import write_context
from benchnuke.execute.harbor import HarborBackend
from benchnuke.ingest.harbor import ingest_harbor_task
from benchnuke.models import (
    AuditDocument,
    Requirement,
    RequirementKind,
)
from benchnuke.pipeline import run_mechanical_audit
from benchnuke.preflight import check_task
from benchnuke.stages.budget import AUDIT_TIMEOUT_SEC
from benchnuke.work import default_work_dir

app = typer.Typer(help="Audit Harbor tasks for verifier gaps.", no_args_is_help=True)


def _load_dotenv() -> None:
    """Load KEY=VALUE from .env without overriding the process environment."""
    candidates = (
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[2] / ".env",
    )
    seen: set[Path] = set()
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        for raw in resolved.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = value


@app.callback()
def _root(
    version: bool = typer.Option(False, "--version", help="Show version and exit."),
) -> None:
    _load_dotenv()
    if version:
        typer.echo(__version__)
        raise typer.Exit()


@app.command()
def schema() -> None:
    """Print BAF 1.0 JSON Schema."""
    typer.echo(json.dumps(AuditDocument.model_json_schema(), indent=2))


@app.command()
def watch(
    work_dir: Path | None = typer.Argument(
        None,
        help="Audit work directory. Defaults to newest audits/*/audit.json.",
    ),
) -> None:
    """Stage-wise TUI for a running or finished audit."""
    from benchnuke.watch_tui import run_watch

    try:
        run_watch(work_dir)
    except FileNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


@app.command()
def ingest(task: Path = typer.Argument(..., exists=True, file_okay=False)) -> None:
    """Load a Harbor task directory and print its id."""
    artifact = ingest_harbor_task(task)
    typer.echo(artifact.task_id)


@app.command("context")
def context_cmd(
    task: Path = typer.Argument(..., exists=True, file_okay=False),
    out: Path | None = typer.Option(None, "--out", help="Write context markdown here."),
) -> None:
    """Dump instruction, tests, and gold for stage agents."""
    artifact = ingest_harbor_task(task)
    dest = out or default_work_dir(artifact.task_id) / "context.md"
    write_context(artifact, dest)
    typer.echo(str(dest))


@app.command()
def check(task: Path = typer.Argument(..., exists=True, file_okay=False)) -> None:
    """Preflight: Harbor nop fails; Harbor oracle on gold passes."""
    artifact = ingest_harbor_task(task)
    work = default_work_dir(artifact.task_id)
    empty = work / "empty"
    empty.mkdir(parents=True, exist_ok=True)
    check_task(artifact, HarborBackend(), empty, log_dir=work / "preflight")
    typer.echo(f"preflight ok: {artifact.task_id}")


@app.command()
def grade(
    task: Path = typer.Argument(..., exists=True, file_okay=False),
    artifact_dir: Path = typer.Option(..., "--artifact", exists=True, file_okay=False),
) -> None:
    """Run Harbor oracle (or nop if artifact is empty) against an implementation."""
    loaded = ingest_harbor_task(task)
    result = HarborBackend().grade(loaded, artifact_dir)
    typer.echo(result.value)
    raise typer.Exit(0 if result.value == "pass" else 1)


@app.command()
def prove(
    task: Path = typer.Argument(..., exists=True, file_okay=False),
    artifact_dir: Path = typer.Option(..., "--artifact", exists=True, file_okay=False),
    countertest: Path = typer.Option(..., "--countertest", exists=True, dir_okay=False),
    requirement_id: str = typer.Option(..., "--requirement-id"),
    statement: str = typer.Option(..., "--statement"),
    work_dir: Path | None = typer.Option(None, "--work-dir"),
) -> None:
    """Build the 4-cell table and write a BAF report."""
    requirement = Requirement(
        id=requirement_id,
        statement=statement,
        kind=RequirementKind.EXPLICIT,
        evidence=statement,
        source_file="instruction.md",
    )
    output = run_mechanical_audit(
        task,
        artifact_dir=artifact_dir,
        countertest_path=countertest,
        requirement=requirement,
        work_dir=work_dir,
        backend=HarborBackend(),
    )
    typer.echo(str(output / "audit.json"))


@app.command()
def audit(
    task: Path = typer.Argument(..., exists=True, file_okay=False),
    no_grok: bool = typer.Option(
        False,
        "--no-grok",
        help="Skip grok -p and grade a provided artifact (mechanical path).",
    ),
    artifact_dir: Path | None = typer.Option(None, "--artifact"),
    countertest: Path | None = typer.Option(None, "--countertest"),
    requirement_id: str | None = typer.Option(None, "--requirement-id"),
    statement: str | None = typer.Option(None, "--statement"),
    work_dir: Path | None = typer.Option(None, "--work-dir"),
    harness: str = typer.Option(
        "pi",
        "--harness",
        help="LLM harness: pi (default) or grok.",
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        help="Model id. For Pi+OpenRouter: anthropic/claude-sonnet-4",
    ),
    provider: str = typer.Option(
        "openrouter",
        "--provider",
        help="Pi provider (default openrouter).",
    ),
    fresh: bool = typer.Option(
        False,
        "--fresh",
        help="Ignore existing work-dir outputs and rerun every LLM stage.",
    ),
    timeout_sec: int = typer.Option(
        AUDIT_TIMEOUT_SEC,
        "--timeout-sec",
        help=(
            "Awake-time budget for the whole audit (default 1 hour). Enforced "
            "between stages and as each stage's subprocess timeout; the clock "
            "pauses during system sleep on macOS, so audits survive laptop sleep."
        ),
    ),
) -> None:
    """Run the full audit. LLM stages use Pi+OpenRouter by default."""
    if os.environ.get("BENCHNUKE_IN_AUDIT") == "1":
        raise typer.BadParameter(
            "nested benchnuke audit is refused (BENCHNUKE_IN_AUDIT=1)"
        )
    if no_grok:
        if artifact_dir is None or countertest is None:
            raise typer.BadParameter("--no-grok requires --artifact and --countertest")
        if requirement_id is None or statement is None:
            raise typer.BadParameter("--no-grok requires --requirement-id and --statement")
        loaded = ingest_harbor_task(task)
        if statement.strip() not in loaded.instruction:
            raise typer.BadParameter(
                "requirement --statement must appear verbatim in instruction.md"
            )
        requirement = Requirement(
            id=requirement_id,
            statement=statement,
            kind=RequirementKind.EXPLICIT,
            evidence=statement,
            source_file="instruction.md",
        )
        output = run_mechanical_audit(
            task,
            artifact_dir=artifact_dir,
            countertest_path=countertest,
            requirement=requirement,
            work_dir=work_dir,
            backend=HarborBackend(),
        )
        typer.echo(str(output / "audit.json"))
        return
    from benchnuke.grok_audit import run_grok_audit

    output = run_grok_audit(
        task,
        work_dir=work_dir,
        backend=HarborBackend(),
        harness=harness,
        model=model,
        provider=provider,
        fresh=fresh,
        timeout_sec=timeout_sec,
    )
    typer.echo(str(output / "audit.json"))
