from __future__ import annotations

import json

from benchnuke.models import Requirement
from benchnuke.stages.base import AuditContext


class GradeStage:
    def __init__(self, requirement: Requirement) -> None:
        self.requirement = requirement
        self.name = f"grade-{requirement.id}"

    def done(self, ctx: AuditContext) -> bool:
        return ctx.work.official_grade(self.requirement.id).is_file()

    def run(self, ctx: AuditContext) -> None:
        artifact = ctx.work.artifact(self.requirement.id)
        result = ctx.backend.grade(
            ctx.task,
            artifact,
            log_dir=ctx.work.run_dir(self.name),
        )
        path = ctx.work.official_grade(self.requirement.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"result": result.value}) + "\n",
            encoding="utf-8",
        )
        ctx.document.summary.attacks_attempted = ctx.work.graded_count()
        ctx.save()


def official_passed(ctx: AuditContext, req_id: str) -> bool:
    path = ctx.work.official_grade(req_id)
    if not path.is_file():
        return False
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("result") == "pass"
