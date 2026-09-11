SPEC_TOOLS = ("read_file", "grep", "list_dir", "search_replace", "write")
ATTACK_TOOLS = (
    "read_file",
    "grep",
    "list_dir",
    "search_replace",
    "write",
    "run_terminal_cmd",
)
NO_AUDIT = "Do not invoke benchnuke audit. Never recurse into a full audit."
SPEC_TURNS = 200
COVERAGE_TURNS = 200
ATTACK_TURNS = 400
COUNTERTEST_TURNS = 400
#: Whole-audit budget in seconds of awake time: the deadline is monotonic,
#: which pauses during system sleep on macOS, so audits survive laptop sleep.
#: Enforced between stages (maybe_run) and as each stage's subprocess timeout.
AUDIT_TIMEOUT_SEC = 60 * 60
#: pi --thinking level for spec-extract and coverage: subtle coverage
#: judgments need real reasoning; attack/countertest stay at the pi default.
SPEC_THINKING = "high"
STAGE_MAX_ATTEMPTS = 3  # 1 initial run + 2 retries of operational failures
STAGE_RETRY_BACKOFF_SEC = (5.0, 15.0)  # sleep before retry attempt 2 and 3
