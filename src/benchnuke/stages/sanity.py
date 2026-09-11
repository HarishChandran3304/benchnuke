from __future__ import annotations

from benchnuke.preflight import check_task
from benchnuke.stages.base import AuditContext


class SanityStage:
    name = "sanity"

    def done(self, ctx: AuditContext) -> bool:
        return ctx.work.preflight_ok.is_file()

    def run(self, ctx: AuditContext) -> None:
        ctx.work.empty.mkdir(parents=True, exist_ok=True)
        ctx.work.preflight.mkdir(parents=True, exist_ok=True)
        check_task(
            ctx.task,
            ctx.backend,
            ctx.work.empty,
            log_dir=ctx.work.preflight,
        )
        ctx.work.preflight_ok.write_text("1\n", encoding="utf-8")
