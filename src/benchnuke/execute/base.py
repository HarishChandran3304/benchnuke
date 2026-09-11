from __future__ import annotations

from pathlib import Path
from typing import Protocol

from benchnuke.ingest.harbor import AuditTask
from benchnuke.models import PassFail


class VerifierBackend(Protocol):
    def grade(
        self,
        task: AuditTask,
        artifact_dir: Path,
        log_dir: Path | None = None,
    ) -> PassFail:
        """Run the official verifier against an implementation directory."""

    def countertest(
        self,
        task: AuditTask,
        artifact_dir: Path,
        countertest_path: Path,
        log_dir: Path | None = None,
    ) -> PassFail:
        """Run a benchnuke counter-test; does not touch official tests/."""
