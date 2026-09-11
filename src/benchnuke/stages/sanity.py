from __future__ import annotations

from benchnuke.stage0 import check_task
from benchnuke.stages.base import AuditContext


class SanityStage:
    name = "sanity"

    def done(self, ctx: AuditContext) -> bool:
        return ctx.work.stage0_ok.is_file()

    def run(self, ctx: AuditContext) -> None:
        ctx.work.empty.mkdir(parents=True, exist_ok=True)
        ctx.work.stage0.mkdir(parents=True, exist_ok=True)
        check_task(
            ctx.task,
            ctx.backend,
            ctx.work.empty,
            log_dir=ctx.work.stage0,
        )
        ctx.work.stage0_ok.write_text("1\n", encoding="utf-8")
