from __future__ import annotations

from benchnuke.models import Requirement
from benchnuke.stages.base import AuditContext, run_llm_stage
from benchnuke.stages.budget import ATTACK_TOOLS, COUNTERTEST_TURNS


class CountertestStage:
    def __init__(self, requirement: Requirement) -> None:
        self.requirement = requirement
        self.name = f"countertest-{requirement.id}"

    def done(self, ctx: AuditContext) -> bool:
        return ctx.work.run_ok(self.name).is_file()

    def run(self, ctx: AuditContext) -> None:
        run_llm_stage(
            ctx,
            name=self.name,
            prompt_name="countertest.md",
            tools=ATTACK_TOOLS,
            max_turns=COUNTERTEST_TURNS,
            replacements={
                "requirement_id": self.requirement.id,
                "requirement_statement": self.requirement.statement,
                "task_root": str(ctx.task.root),
            },
        )
