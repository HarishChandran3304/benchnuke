"""Parse Harbor/Pier verifier reward files."""

from __future__ import annotations

import json
from pathlib import Path

from benchnuke.models import PassFail


def parse_reward(verifier_dir: Path) -> PassFail:
    json_path = verifier_dir / "reward.json"
    txt_path = verifier_dir / "reward.txt"
    if json_path.is_file():
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and "reward" in payload:
            return _from_number(payload["reward"])
        if isinstance(payload, (int, float)):
            return _from_number(payload)
        raise ValueError(f"unrecognized reward.json in {verifier_dir}")
    if txt_path.is_file():
        raw = txt_path.read_text(encoding="utf-8").strip().splitlines()[0]
        return _from_number(float(raw))
    raise FileNotFoundError(f"no reward.txt or reward.json in {verifier_dir}")


def _from_number(value: float) -> PassFail:
    return PassFail.PASS if float(value) >= 1.0 else PassFail.FAIL
