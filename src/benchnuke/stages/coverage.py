from __future__ import annotations

from benchnuke.errors import SchemaError
from benchnuke.models import CoverageLevel, CoverageRow
from benchnuke.stages.base import AuditContext, run_llm_stage
from benchnuke.stages.budget import (
    COVERAGE_SAMPLES,
    COVERAGE_TURNS,
    SPEC_THINKING,
    SPEC_TOOLS,
)

#: Suspicion order across samples: the most-suspicious row wins, so a
#: requirement is gapped if ANY pass doubts it (union of doubt).
_SUSPICION = {
    CoverageLevel.NONE: 0,
    CoverageLevel.PARTIAL: 1,
    CoverageLevel.UNKNOWN: 2,
    CoverageLevel.INDIRECT: 3,
    CoverageLevel.FULL: 4,
}


def merge_coverage_samples(samples: list[list[CoverageRow]]) -> list[CoverageRow]:
    """Union N coverage passes, keeping each requirement's most-suspicious row."""
    merged: dict[str, CoverageRow] = {}
    for rows in samples:
        for row in rows:
            current = merged.get(row.requirement_id)
            if current is None or (
                _SUSPICION[row.coverage] < _SUSPICION[current.coverage]
            ):
                merged[row.requirement_id] = row
    return list(merged.values())


class CoverageStage:
    name = "coverage"

    def done(self, ctx: AuditContext) -> bool:
        return ctx.work.coverage.is_file()

    def run(self, ctx: AuditContext) -> None:
        from benchnuke.pipeline import CoverageFile, load_coverage

        samples: list[list[CoverageRow]] = []
        for _ in range(COVERAGE_SAMPLES):
            run_llm_stage(
                ctx,
                name=self.name,
                prompt_name="coverage.md",
                tools=SPEC_TOOLS,
                max_turns=COVERAGE_TURNS,
                thinking=SPEC_THINKING,
            )
            if not ctx.work.coverage.is_file():
                raise SchemaError("coverage stage did not write coverage.json")
            feedback = ctx.work.root / "prompts" / f"{self.name}.error.txt"
            try:
                samples.append(load_coverage(ctx.work.coverage).coverage)
            except SchemaError as exc:
                feedback.write_text(str(exc), encoding="utf-8")
                raise
            ctx.work.coverage.unlink()
        merged = merge_coverage_samples(samples)
        feedback = ctx.work.root / "prompts" / f"{self.name}.error.txt"
        if feedback.is_file():
            feedback.unlink()
        ctx.work.coverage.write_text(
            CoverageFile(coverage=merged).model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        ctx.document.coverage = merged
        ctx.save()
