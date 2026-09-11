from __future__ import annotations

from benchnuke.report import NO_BYPASS_SENTENCE, write_empty_report
from benchnuke.stages.base import AuditContext


class EmptyReportStage:
    name = "report"

    def done(self, ctx: AuditContext) -> bool:
        return ctx.work.run_ok(self.name).is_file()

    def run(self, ctx: AuditContext) -> None:
        write_empty_report(
            output_dir=ctx.work.audit_output,
            task_id=ctx.task.task_id,
            findings=ctx.document.findings,
        )
        if NO_BYPASS_SENTENCE not in ctx.document.notes:
            ctx.document.notes.append(NO_BYPASS_SENTENCE)
            ctx.save()
        log_dir = ctx.work.run_dir(self.name)
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "ok").write_text("1\n", encoding="utf-8")
