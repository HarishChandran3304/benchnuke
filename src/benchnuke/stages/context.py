from __future__ import annotations

from benchnuke.context import write_context
from benchnuke.stages.base import AuditContext


class ContextStage:
    name = "context"

    def done(self, ctx: AuditContext) -> bool:
        return ctx.work.context.is_file()

    def run(self, ctx: AuditContext) -> None:
        write_context(ctx.task, ctx.work.context)
