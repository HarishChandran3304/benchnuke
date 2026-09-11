from __future__ import annotations

import json

from benchnuke.models import FindingStatus, Requirement
from benchnuke.pipeline import run_mechanical_audit
from benchnuke.stages.base import AuditContext


class ProveStage:
    def __init__(self, requirement: Requirement) -> None:
        self.requirement = requirement
        self.name = f"prove-{requirement.id}"

    def done(self, ctx: AuditContext) -> bool:
        return ctx.work.prove_ok(self.requirement.id).is_file()

    def run(self, ctx: AuditContext) -> None:
        counter = ctx.work.countertest(self.requirement.id)
        if not counter.is_file():
            path = ctx.work.prove_ok(self.requirement.id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"status": "skipped", "reason": "no countertest.py"}) + "\n",
                encoding="utf-8",
            )
            return
        output = run_mechanical_audit(
            ctx.task.root,
            artifact_dir=ctx.work.artifact(self.requirement.id),
            countertest_path=counter,
            requirement=self.requirement,
            work_dir=ctx.work.root,
            backend=ctx.backend,
            skip_sanity=True,
        )
        payload = json.loads((output / "audit.json").read_text(encoding="utf-8"))
        status = payload.get("findings", [{}])[0].get("status")
        path = ctx.work.prove_ok(self.requirement.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"status": status, "audit_json": str(output / "audit.json")})
            + "\n",
            encoding="utf-8",
        )


def prove_confirmed(ctx: AuditContext, req_id: str) -> bool:
    path = ctx.work.prove_ok(req_id)
    if not path.is_file():
        return False
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("status") == FindingStatus.CONFIRMED.value
