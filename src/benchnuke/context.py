"""Dump task context for stage agents."""

from __future__ import annotations

from pathlib import Path

from benchnuke.ingest.harbor import AuditTask


def render_context(task: AuditTask) -> str:
    tests = _read_dir(task.tests_dir)
    solution = _read_dir(task.solution_dir) if task.solution_dir else "(no reference solution)"
    return (
        f"# Task `{task.task_id}`\n\n"
        f"Root: `{task.root}`\n\n"
        f"## instruction.md\n\n{task.instruction.strip()}\n\n"
        f"## tests/\n\n{tests}\n\n"
        f"## solution/\n\n{solution}\n"
    )


def write_context(task: AuditTask, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render_context(task), encoding="utf-8")
    return dest


def _read_dir(path: Path) -> str:
    parts: list[str] = []
    for file in sorted(path.rglob("*")):
        if not file.is_file():
            continue
        rel = file.relative_to(path)
        if file.suffix in {".py", ".sh", ".md", ".txt", ".toml", ".json"} or file.name == "test.sh":
            parts.append(f"### {rel}\n\n```\n{file.read_text(encoding='utf-8')}```\n")
    return "\n".join(parts) if parts else "(empty)"
