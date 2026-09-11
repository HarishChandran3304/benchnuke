"""Stage protocol: each step has a name, a done() check, and run()."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from benchnuke.agent.base import HeadlessAgent, StageSpec
from benchnuke.errors import AgentRunnerError, is_retryable
from benchnuke.execute.base import VerifierBackend
from benchnuke.ingest.harbor import AuditTask
from benchnuke.models import AuditDocument
from benchnuke.prompts import load_prompt
from benchnuke.report import load_audit_document, save_audit_document, upsert_stage
from benchnuke.stages.budget import (
    AUDIT_TIMEOUT_SEC,
    NO_AUDIT,
    STAGE_MAX_ATTEMPTS,
    STAGE_RETRY_BACKOFF_SEC,
)
from benchnuke.stages.layout import WorkLayout


@dataclass
class AuditContext:
    task: AuditTask
    work: WorkLayout
    backend: VerifierBackend
    runner: HeadlessAgent
    document: AuditDocument
    fresh: bool = False
    # Monotonic clock: pauses during system sleep on macOS, so the audit
    # budget counts awake time and runs survive laptop sleep.
    deadline_monotonic: float = field(
        default_factory=lambda: time.monotonic() + AUDIT_TIMEOUT_SEC
    )

    def remaining_sec(self) -> float:
        return max(0.0, self.deadline_monotonic - time.monotonic())

    def save(self) -> None:
        save_audit_document(self.work.audit_json, self.document)

    def reload_outputs(self) -> None:
        disk = load_audit_document(self.work.audit_json)
        if disk is None:
            return
        self.document.findings = disk.findings
        self.document.specification = disk.specification
        self.document.coverage = disk.coverage
        self.document.summary = disk.summary
        if disk.notes:
            self.document.notes = disk.notes


class Stage(Protocol):
    name: str

    def done(self, ctx: AuditContext) -> bool: ...

    def run(self, ctx: AuditContext) -> None: ...


def maybe_run(stage: Stage, ctx: AuditContext) -> str:
    """Run or skip. Returns 'skip' or 'run'.

    Operational failures (timeouts, harbor/docker flakiness, malformed LLM
    JSON) are retried up to STAGE_MAX_ATTEMPTS with backoff, never past the
    audit deadline. Findings and config errors fail on the first attempt.
    """
    if not ctx.fresh and stage.done(ctx):
        upsert_stage(ctx.document, stage.name, "skip")
        ctx.save()
        return "skip"
    if ctx.remaining_sec() <= 0:
        upsert_stage(ctx.document, stage.name, "error", "audit time budget exceeded")
        ctx.document.run_status = "failed"
        ctx.save()
        raise AgentRunnerError(
            f"audit time budget exceeded before stage {stage.name}"
        )
    upsert_stage(ctx.document, stage.name, "running")
    ctx.save()
    attempt = 0
    while True:
        attempt += 1
        try:
            stage.run(ctx)
            break
        except Exception as exc:
            if not _should_retry(exc, attempt, ctx):
                note = f" (failed after {attempt} attempts)" if attempt > 1 else ""
                upsert_stage(ctx.document, stage.name, "error", f"{exc}{note}")
                ctx.document.run_status = "failed"
                ctx.save()
                raise
            backoff = _retry_backoff(attempt)
            upsert_stage(
                ctx.document,
                stage.name,
                "running",
                f"attempt {attempt} failed: {exc}; retrying in {backoff:.0f}s",
            )
            ctx.save()
            time.sleep(min(backoff, ctx.remaining_sec()))
    ctx.reload_outputs()
    upsert_stage(ctx.document, stage.name, "ok")
    ctx.save()
    return "run"


def _should_retry(exc: BaseException, attempt: int, ctx: AuditContext) -> bool:
    """Self-heal operational failures only, and never past the audit deadline."""
    if attempt >= STAGE_MAX_ATTEMPTS or not is_retryable(exc):
        return False
    return ctx.remaining_sec() > 0


def _retry_backoff(failed_attempt: int) -> float:
    index = min(failed_attempt - 1, len(STAGE_RETRY_BACKOFF_SEC) - 1)
    return STAGE_RETRY_BACKOFF_SEC[index]


def run_llm_stage(
    ctx: AuditContext,
    *,
    name: str,
    prompt_name: str,
    tools: tuple[str, ...],
    max_turns: int,
    replacements: dict[str, str] | None = None,
    thinking: str | None = None,
) -> None:
    feedback_path = ctx.work.root / "prompts" / f"{name}.error.txt"
    error_feedback = ""
    if feedback_path.is_file():
        error_feedback = (
            "\n\nYour previous attempt produced an invalid output file. Fix it:\n"
            + feedback_path.read_text(encoding="utf-8")
        )
    merged = {**(replacements or {}), "error_feedback": error_feedback}
    prompt_text = load_prompt(prompt_name, **merged)
    prompt_file = ctx.work.root / "prompts" / f"{name}.md"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(prompt_text, encoding="utf-8")
    log_dir = ctx.work.run_dir(name)
    ctx.runner.run(
        StageSpec(
            name=name,
            prompt_file=prompt_file,
            cwd=ctx.work.root,
            max_turns=max_turns,
            tools=tools,
            rules=NO_AUDIT,
            timeout_sec=max(1, int(ctx.remaining_sec())),
            thinking=thinking,
        ),
        log_dir=log_dir,
    )
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "ok").write_text("1\n", encoding="utf-8")


def artifact_ready(artifact: Path) -> bool:
    if not artifact.is_dir():
        return False
    if (artifact / "solve.sh").is_file() or (artifact / "solution.patch").is_file():
        return True
    for path in artifact.iterdir():
        if not path.is_file():
            continue
        if path.name in {"countertest.py", "probe.py"} or path.name.startswith("test_"):
            continue
        if path.suffix in {".py", ".patch", ".diff"}:
            return True
    return False
