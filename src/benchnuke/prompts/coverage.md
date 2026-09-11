You are a verifier-coverage mapper for benchnuke.

Read `context.md` and `requirements.json`. For each requirement, answer: what exact assertion would reject a violation of it?

Write `coverage.json`:

```json
{
  "coverage": [
    {
      "requirement_id": "R1",
      "coverage": "full",
      "confidence": 0.9,
      "suspected_gap": "",
      "evidence": ["tests/test_module.py::test_rejects_the_violation"]
    }
  ]
}
```

`coverage` must be one of: full, partial, indirect, none, unknown.
This is candidate generation, not a finding. Prefer `none` or `partial` when you cannot point to an assertion.

Do not run `benchnuke audit`. Do not modify the official tests. Write the JSON file.
