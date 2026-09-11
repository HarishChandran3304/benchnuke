You are a counter-test generator for benchnuke.

Requirement `{{requirement_id}}`: {{requirement_statement}}

An adversarial implementation is in `artifacts/{{requirement_id}}/`. It already **passes** the official Harbor verifier.

Write `artifacts/{{requirement_id}}/countertest.py` as a **plain Python script** (no pytest):

- `main() -> int` returning 0 on success, 1 on failure
- `if __name__ == "__main__": raise SystemExit(main())`
- Import the same module the official tests import. benchnuke runs the script with `PYTHONPATH=/app`, so the module under test is importable directly — no `sys.path` setup needed.

The script must:

1. Exit 1 on the adversarial implementation (it violates the requirement).
2. Exit 0 on the reference solution in the task `solution/` directory.

benchnuke will run this through Harbor (`harbor run -a oracle` on a staged task whose `tests/` is this script). Do not modify official tests. Do not run `benchnuke audit`. Do not run pytest.
