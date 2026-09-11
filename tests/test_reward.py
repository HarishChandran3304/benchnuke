from __future__ import annotations

from pathlib import Path

import pytest

from benchnuke.execute.reward import parse_reward
from benchnuke.models import PassFail


def test_parse_reward_txt(tmp_path: Path) -> None:
    path = tmp_path / "reward.txt"
    path.write_text("1\n", encoding="utf-8")
    assert parse_reward(tmp_path) is PassFail.PASS
    path.write_text("0\n", encoding="utf-8")
    assert parse_reward(tmp_path) is PassFail.FAIL


def test_parse_reward_json_binary(tmp_path: Path) -> None:
    path = tmp_path / "reward.json"
    path.write_text('{"reward": 1.0}\n', encoding="utf-8")
    assert parse_reward(tmp_path) is PassFail.PASS
    path.write_text('{"reward": 0}\n', encoding="utf-8")
    assert parse_reward(tmp_path) is PassFail.FAIL


def test_parse_reward_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        parse_reward(tmp_path)
