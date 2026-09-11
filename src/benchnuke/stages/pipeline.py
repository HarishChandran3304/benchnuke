"""Run named, resumable stages in order."""

from __future__ import annotations

import time
from pathlib import Path

from benchnuke.agent.base import HeadlessAgent
from benchnuke.agent.factory import select_runner
from benchnuke.execute.base import VerifierBackend
from benchnuke.execute.harbor import HarborBackend
from benchnuke.ingest.harbor import ingest_harbor_task
from benchnuke.models import AuditDocument, TaskRef
from benchnuke.pipeline import (
    attackable_requirement_ids,
    load_coverage,
    load_requirements,
    skipped_process_requirement_ids,
)
from benchnuke.report import load_audit_document, recompute_summary, save_audit_document
from benchnuke.stages.attack import AttackStage
from benchnuke.stages.base import AuditContext, maybe_run
from benchnuke.stages.budget import AUDIT_TIMEOUT_SEC
from benchnuke.stages.context import ContextStage
from benchnuke.stages.countertest import CountertestStage
from benchnuke.stages.coverage import CoverageStage
from benchnuke.stages.grade import GradeStage, official_passed
from benchnuke.stages.layout import WorkLayout, find_run_for_task
from benchnuke.stages.prove import ProveStage, prove_confirmed
from benchnuke.stages.report import EmptyReportStage
from benchnuke.stages.sanity import SanityStage
from benchnuke.stages.spec import SpecStage
from benchnuke.work import default_work_dir


def run_audit(
    task_path: Path,
    *,
    work_dir: Path | None = None,
    runner: HeadlessAgent | None = None,
    backend: VerifierBackend | None = None,
    harness: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    fresh: bool = False,
    timeout_sec: int = AUDIT_TIMEOUT_SEC,
) -> Path:
    task = ingest_harbor_task(task_path)
    resolved = work_dir
    if resolved is None and not fresh:
        resolved = find_run_for_task(task.task_id)
    work = WorkLayout(resolved or default_work_dir(task.task_id))
    work.root.mkdir(parents=True, exist_ok=True)
    document = None if fresh else load_audit_document(work.audit_json)
    if document is None or document.task.id != task.task_id:
        document = AuditDocument(
            task=TaskRef(id=task.task_id, source_format="harbor"),
            work_dir=str(work.root.resolve()),
            task_path=str(Path(task_path).resolve()),
            run_status="running",
        )
    document.work_dir = str(work.root.resolve())
    document.task_path = str(Path(task_path).resolve())
    document.run_status = "running"
    save_audit_document(work.audit_json, document)
    last_ok = next(
        (row.name for row in reversed(document.stages) if row.status in {"ok", "skip"}),
        None,
    )
    if last_ok:
        print(f"resuming {work.root} (last finished: {last_ok})")
    ctx = AuditContext(
        task=task,
        work=work,
        backend=backend or HarborBackend(),
        runner=runner or select_runner(harness, model=model, provider=provider),
        document=document,
        fresh=fresh,
        deadline_monotonic=time.monotonic() + timeout_sec,
    )
    log: list[str] = []
    for stage in (ContextStage(), SanityStage(), SpecStage(), CoverageStage()):
        log.append(f"{stage.name}:{maybe_run(stage, ctx)}")

    requirements = load_requirements(work.requirements)
    coverage = load_coverage(work.coverage)
    by_id = {item.id: item for item in requirements.requirements}
    document.summary = recompute_summary(
        document.summary,
        specification=document.specification,
        coverage=document.coverage,
        findings=document.findings,
        attacks_attempted=ctx.work.graded_count(),
    )
    ctx.save()
    skipped = skipped_process_requirement_ids(coverage, requirements)
    if skipped:
        note = f"skipped process requirements (not attackable): {', '.join(skipped)}"
        print(note)
        if note not in document.notes:
            document.notes.append(note)
    confirmed_path: Path | None = None
    for req_id in attackable_requirement_ids(coverage, requirements):
        requirement = by_id.get(req_id)
        if requirement is None:
            continue
        work.artifact(req_id).mkdir(parents=True, exist_ok=True)
        for stage in (
            AttackStage(requirement),
            GradeStage(requirement),
        ):
            log.append(f"{stage.name}:{maybe_run(stage, ctx)}")
        if not official_passed(ctx, req_id):
            continue
        counter = CountertestStage(requirement)
        log.append(f"{counter.name}:{maybe_run(counter, ctx)}")
        prove = ProveStage(requirement)
        log.append(f"{prove.name}:{maybe_run(prove, ctx)}")
        if prove_confirmed(ctx, req_id):
            confirmed_path = work.audit_output
            break

    if confirmed_path is None:
        log.append(f"report:{maybe_run(EmptyReportStage(), ctx)}")
        confirmed_path = work.audit_output
    ctx.document.summary = recompute_summary(
        ctx.document.summary,
        specification=ctx.document.specification,
        coverage=ctx.document.coverage,
        findings=ctx.document.findings,
        attacks_attempted=max(ctx.work.graded_count(), len(ctx.document.findings)),
    )
    ctx.document.run_status = "completed"
    ctx.save()
    return confirmed_path
