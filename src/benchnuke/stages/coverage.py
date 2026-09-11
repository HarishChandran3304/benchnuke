from __future__ import annotations

from benchnuke.errors import SchemaError
from benchnuke.stages.base import AuditContext, run_llm_stage
from benchnuke.stages.budget import COVERAGE_TURNS, SPEC_TOOLS


class CoverageStage:
    name = "coverage"

    def done(self, ctx: AuditContext) -> bool:
        return ctx.work.coverage.is_file()

    def run(self, ctx: AuditContext) -> None:
        run_llm_stage(
            ctx,
            name=self.name,
            prompt_name="coverage.md",
            tools=SPEC_TOOLS,
            max_turns=COVERAGE_TURNS,
        )
        if not ctx.work.coverage.is_file():
            raise SchemaError("coverage stage did not write coverage.json")
        from benchnuke.pipeline import load_coverage

        ctx.document.coverage = load_coverage(ctx.work.coverage).coverage
        ctx.save()
