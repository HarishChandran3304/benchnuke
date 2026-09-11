"""benchnuke errors."""

from __future__ import annotations

import subprocess

#: Finding classes a GradeError may carry. These are real findings, not
#: operational failures: fail loudly, never retry (locked methodology).
FINDING_GRADE_MARKERS = ("reference_inconsistency", "verifier_infrastructure")

#: GradeError message fragments that mean operational verifier flakiness
#: (harbor/pier nonzero exit, missing reward file from a flaky docker run).
_OPERATIONAL_GRADE_MARKERS = ("harbor run failed", "no Harbor verifier reward")

#: Runner error fragments that retrying cannot fix (missing binary, wall clock).
_NON_OPERATIONAL_RUNNER_MARKERS = ("binary not found", "wall clock")


class BenchnukeError(Exception):
    """Base error. Conservative default: never retried."""

    retryable = False


class TaskIngestError(BenchnukeError):
    """Harbor task directory is missing required files."""


class GradeError(BenchnukeError):
    """Official verifier could not be executed.

    Retryable only when the verifier runner itself flaked (nonzero exit,
    missing reward files). A GradeError carrying a finding class
    (reference_inconsistency / verifier_infrastructure) is a real finding.
    """

    def __init__(self, message: str, *, retryable: bool | None = None) -> None:
        super().__init__(message)
        if retryable is None:
            retryable = not any(
                marker in message for marker in FINDING_GRADE_MARKERS
            ) and any(marker in message for marker in _OPERATIONAL_GRADE_MARKERS)
        self.retryable = retryable


class AgentRunnerError(BenchnukeError):
    """Headless coding-agent invocation failed."""

    retryable = True


class GrokRunnerError(AgentRunnerError):
    """grok -p invocation failed."""


class SchemaError(BenchnukeError):
    """A stage artifact failed schema validation. Rerunning the stage self-heals."""

    retryable = True


def is_retryable(exc: BaseException) -> bool:
    """True when rerunning the stage may self-heal an operational failure.

    Findings, ingest errors, nested-audit guards, and budget expiry are never
    retried; when unsure, prefer not retrying.
    """
    if isinstance(exc, (TimeoutError, subprocess.TimeoutExpired)):
        return True
    if not isinstance(exc, BenchnukeError) or not exc.retryable:
        return False
    if isinstance(exc, AgentRunnerError):
        text = str(exc).lower()
        return not any(marker in text for marker in _NON_OPERATIONAL_RUNNER_MARKERS)
    return True
