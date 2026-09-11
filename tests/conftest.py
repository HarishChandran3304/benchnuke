from __future__ import annotations

from pathlib import Path

import pytest
from harbor_fake import ScriptedHarborRunner

from benchnuke.execute.harbor import HarborBackend

REPO_ROOT = Path(__file__).resolve().parents[1]
LEAKY_CACHE = REPO_ROOT / "fixtures" / "leaky-cache"


@pytest.fixture
def leaky_cache() -> Path:
    return LEAKY_CACHE


@pytest.fixture
def harbor_backend() -> HarborBackend:
    return HarborBackend(runner=ScriptedHarborRunner())


@pytest.fixture
def patch_cli_harbor(monkeypatch: pytest.MonkeyPatch) -> None:
    def _factory() -> HarborBackend:
        return HarborBackend(runner=ScriptedHarborRunner())

    monkeypatch.setattr("benchnuke.cli.HarborBackend", _factory)
    monkeypatch.setattr("benchnuke.pipeline.HarborBackend", _factory)
