"""Stage 0: nop must fail, reference solution must pass."""

from __future__ import annotations

from pathlib import Path

from benchnuke.errors import GradeError
from benchnuke.execute.base import VerifierBackend
from benchnuke.ingest.harbor import AuditTask
from benchnuke.models import PassFail


def check_task(
    task: AuditTask,
    backend: VerifierBackend,
    empty_dir: Path,
    log_dir: Path | None = None,
) -> None:
    nop = backend.grade(
        task, empty_dir, log_dir=(log_dir / "nop") if log_dir else None
    )
    if nop is PassFail.PASS:
        raise GradeError(
            f"{task.task_id}: nop/empty implementation passed the official verifier "
            "(verifier_infrastructure)"
        )
    if not task.solution_dir:
        return
    gold = backend.grade(
        task,
        task.solution_dir,
        log_dir=(log_dir / "oracle-gold") if log_dir else None,
    )
    if gold is PassFail.FAIL:
        raise GradeError(
            f"{task.task_id}: reference solution failed the official verifier "
            "(reference_inconsistency)"
        )
