"""Audit entry point. Implementation lives in `benchnuke.stages`."""

from __future__ import annotations

from benchnuke.stages.pipeline import run_audit as run_grok_audit  # deprecated alias

__all__ = ["run_grok_audit"]
