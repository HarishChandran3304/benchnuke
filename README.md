# benchnuke

**Verifier red-team for Harbor-format benchmark tasks.** benchnuke finds *executable counterexamples*: implementations that pass the official verifier while violating an explicit, verbatim task requirement — each one proven by a machine-graded four-cell table, never by LLM opinion.

## The question

> Can the official verifier be satisfied by an implementation that violates an explicit task requirement?

Judge-agreement on ordinary solutions says nothing about the verifier's behavior on adversarial ones. benchnuke attacks the verifier directly and keeps only the proofs.

## How it works

```
task dir → preflight → spec extract → coverage ×3 → attack → counter-test → four-cell proof → BAF audit.json + proof bundle
```

- **Preflight** — the empty solution must FAIL and the reference must PASS, or the task itself is broken.
- **Spec extract** — LLM decomposes `instruction.md` into atomic *explicit* requirements (verbatim evidence only; no invented rules).
- **Coverage ×3** — three independent passes ask: *hypothetically, if this requirement were violated on purpose, which exact assertion would fail?* No answer → attack candidate. Candidates only, never a finding.
- **Attack** — a white-box coding agent builds the smallest complete implementation that passes the official verifier while deliberately violating one requirement, iterating against the real grader.
- **Counter-test** — a plain script that must FAIL on the adversarial and PASS on the reference. If gold fails it too, the finding is discarded.
- **Four-cell proof** — the evidence bar (evidence level A):

| | reference solution | adversarial solution |
|---|---|---|
| **official verifier** | PASS | PASS |
| **counter-test** | PASS | FAIL |

Anything less is rejected. Findings accumulate as `F001…` with full bundles (adversarial patch, counter-test, all four cell logs).

**Honesty rules:** only explicit requirements can become confirmed findings · never report "task is clean" — only *"no bypass found under this attack budget"* · grading always runs the official Harbor/Pier boundary, never host-side test runners.

## Install

```bash
uv sync
uv tool install harbor
uv tool install datacurve-pier          # air-gapped tasks (DeepSWE: network_mode=no-network)
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
export OPENROUTER_API_KEY=...           # or .env
# Docker daemon must be running
```

`bn` is an alias for `benchnuke`.

## Usage

Full LLM-driven audit of one task (Pi + OpenRouter by default):

```bash
uv run bn audit <task-dir> --model z-ai/glm-5.3-flash --exhaust --timeout-sec 10800
```

- `--exhaust` attack every gapped requirement (default stops at the first confirmed finding)
- `--fresh` wipe the run dir and start over (resume is the default)
- `--harness grok` fallback agent runtime · `bn check` preflight only · `bn schema` BAF 1.0 JSON Schema

Mechanical path (grade a prebuilt artifact + counter-test, no LLM):

```bash
uv run bn audit fixtures/leaky-cache --no-grok \
  --artifact fixtures/leaky-cache/attacks/R3 \
  --countertest fixtures/leaky-cache/attacks/R3/countertest.py \
  --requirement-id R3 \
  --statement "Failed requests must not be cached."
```

## Output

```
audits/<task>/
  results/audit.json      BAF 1.0 manifest (spec, coverage, findings, summary)
  results/report.md       human report ("Confirmed verifier gaps: N" or the no-bypass sentence)
  results/findings/F00x/  adversarial/, countertest.py, logs/, finding.json
  artifacts/  runs/  prompts/  preflight/  context.md
```

## Development

```bash
uv run pytest        # marker-gated: integration (needs Harbor/Docker), live
uv run ruff check
```

`fixtures/leaky-cache/` is a Harbor task with a deliberately known verifier gap, used end-to-end in tests.

## Results (MVP)

- **5 out of 5 audited DeepSWE tasks (100%) had at least one confirmed verifier bypass** — 16 total.
- **~12% of explicit requirements were adversarially satisfiable** (16 of 138).
- **100% attack→proof conversion (16/16).**

Full evidence bundles in the [**deep-swe-audits**](https://github.com/HarishChandran3304/deep-swe-audits) repo.
