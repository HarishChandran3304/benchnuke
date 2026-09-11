from __future__ import annotations

from pathlib import Path

from benchnuke.models import AuditDocument, TaskRef
from benchnuke.report import save_audit_document
from benchnuke.stages.layout import find_run_for_task


def test_find_run_for_task_picks_newest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    older = tmp_path / "work" / "old"
    newer = tmp_path / "work" / "new"
    for folder, task_id in ((older, "bench/task"), (newer, "bench/task")):
        path = folder / "audit-output" / "audit.json"
        doc = AuditDocument(task=TaskRef(id=task_id), work_dir=str(folder))
        save_audit_document(path, doc)
    other = tmp_path / "work" / "other" / "audit-output" / "audit.json"
    save_audit_document(
        other, AuditDocument(task=TaskRef(id="bench/other"), work_dir="x")
    )
    found = find_run_for_task("bench/task", base=tmp_path / "work")
    assert found == newer.resolve() or found == newer
    assert found is not None
    assert found.name == "new"


def test_find_run_for_task_ignores_id_in_notes(tmp_path: Path) -> None:
    base = tmp_path / "work"
    path = base / "notes-run" / "audit-output" / "audit.json"
    doc = AuditDocument(
        task=TaskRef(id="bench/other"),
        work_dir="x",
        notes=["see bench/task for the original failure"],
    )
    save_audit_document(path, doc)
    assert find_run_for_task("bench/task", base=base) is None


def test_find_run_for_task_does_not_match_id_prefix(tmp_path: Path) -> None:
    base = tmp_path / "work"
    path = base / "prefixed" / "audit-output" / "audit.json"
    save_audit_document(
        path, AuditDocument(task=TaskRef(id="bench/task-2"), work_dir="x")
    )
    assert find_run_for_task("bench/task", base=base) is None


def test_find_run_for_task_skips_invalid_json(tmp_path: Path) -> None:
    base = tmp_path / "work"
    truncated = base / "truncated" / "audit-output"
    truncated.mkdir(parents=True)
    (truncated / "audit.json").write_text(
        '{"task": {"id": "bench/task"', encoding="utf-8"
    )
    bare = base / "bare" / "audit-output"
    bare.mkdir(parents=True)
    (bare / "audit.json").write_text('"bench/task"\n', encoding="utf-8")
    good = base / "good" / "audit-output" / "audit.json"
    save_audit_document(
        good, AuditDocument(task=TaskRef(id="bench/task"), work_dir="x")
    )
    found = find_run_for_task("bench/task", base=base)
    assert found is not None
    assert found.name == "good"
