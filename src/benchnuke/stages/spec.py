from __future__ import annotations

from benchnuke.errors import SchemaError
from benchnuke.stages.base import AuditContext, run_llm_stage
from benchnuke.stages.budget import SPEC_THINKING, SPEC_TOOLS, SPEC_TURNS


class SpecStage:
    name = "spec-extract"

    def done(self, ctx: AuditContext) -> bool:
        return ctx.work.requirements.is_file()

    def run(self, ctx: AuditContext) -> None:
        run_llm_stage(
            ctx,
            name=self.name,
            prompt_name="spec_extract.md",
            tools=SPEC_TOOLS,
            max_turns=SPEC_TURNS,
            thinking=SPEC_THINKING,
        )
        if not ctx.work.requirements.is_file():
            raise SchemaError("spec-extract did not write requirements.json")
        from benchnuke.pipeline import load_requirements

        feedback = ctx.work.root / "prompts" / f"{self.name}.error.txt"
        try:
            requirements = load_requirements(ctx.work.requirements).requirements
        except SchemaError as exc:
            feedback.write_text(str(exc), encoding="utf-8")
            raise
        if feedback.is_file():
            feedback.unlink()
        ctx.document.specification = requirements
        ctx.save()
