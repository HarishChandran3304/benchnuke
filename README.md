# benchnuke

Audit Harbor-format coding tasks for **verifier gaps**: implementations that pass the official grader while violating an explicit requirement.

Every official cell is Harbor: `harbor run -a oracle` or `harbor run -a nop`. There is no host-side pytest grader.

## Setup

```bash
cd benchnuke
uv sync
uv tool install harbor
uv tool install datacurve-pier   # DeepSWE air-gapped tasks
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
export OPENROUTER_API_KEY=...
# Docker daemon must be running
```

`bn` is an alias for `benchnuke` (same entry point).

## Run

From `benchnuke/`:

```bash
uv run bn audit fixtures/leaky-cache --no-grok \
  --artifact fixtures/leaky-cache/attacks/R3 \
  --countertest fixtures/leaky-cache/attacks/R3/countertest.py \
  --requirement-id R3 \
  --statement "Failed requests must not be cached."
```

Watch a running audit (stage list + live log tail):

```bash
uv run bn watch
uv run bn watch work/deepswe-fastapi-deprecation/audit-pi
```

Unattended LLM stages use **Pi + OpenRouter** (Harbor/Pier still grade):

```bash
uv run bn audit fixtures/leaky-cache \
  --harness pi --provider openrouter --model anthropic/claude-sonnet-4
```

DeepSWE task (from repo root, Docker required):

```bash
uv run --directory benchnuke bn check ../benchmarks/deep-swe/tasks/fastapi-deprecation-response-headers
uv run --directory benchnuke bn audit ../benchmarks/deep-swe/tasks/fastapi-deprecation-response-headers
```

Smoke the fixture with Harbor directly:

```bash
harbor run -p fixtures/leaky-cache -a oracle -y   # reward 1
harbor run -p fixtures/leaky-cache -a nop -y      # reward 0
```

A confirmed finding is the 4-cell table:

| | Official verifier | Counter-test |
|---|---|---|
| Reference | PASS | PASS |
| Adversarial | PASS | FAIL |

Never report “the task is clean.” Report “no bypass found under this attack budget.”
