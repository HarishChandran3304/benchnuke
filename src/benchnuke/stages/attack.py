from __future__ import annotations

from benchnuke.models import Requirement
from benchnuke.stages.base import AuditContext, artifact_ready, run_llm_stage
from benchnuke.stages.budget import ATTACK_TOOLS, ATTACK_TURNS


class AttackStage:
    def __init__(self, requirement: Requirement) -> None:
        self.requirement = requirement
        self.name = f"attack-{requirement.id}"

    def done(self, ctx: AuditContext) -> bool:
        return artifact_ready(ctx.work.artifact(self.requirement.id))

    def run(self, ctx: AuditContext) -> None:
        artifact = ctx.work.artifact(self.requirement.id)
        artifact.mkdir(parents=True, exist_ok=True)
        run_llm_stage(
            ctx,
            name=self.name,
            prompt_name="attack.md",
            tools=ATTACK_TOOLS,
            max_turns=ATTACK_TURNS,
            replacements={
                "requirement_id": self.requirement.id,
                "requirement_statement": self.requirement.statement,
                "task_root": str(ctx.task.root),
            },
        )
