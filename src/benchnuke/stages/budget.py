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
AUDIT_TIMEOUT_SEC = 60 * 60
STAGE_MAX_ATTEMPTS = 3  # 1 initial run + 2 retries of operational failures
STAGE_RETRY_BACKOFF_SEC = (5.0, 15.0)  # sleep before retry attempt 2 and 3
