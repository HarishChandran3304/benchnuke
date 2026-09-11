from __future__ import annotations

from pathlib import Path


def load_prompt(name: str, **replacements: str) -> str:
    path = Path(__file__).with_name(name)
    text = path.read_text(encoding="utf-8")
    for key, value in replacements.items():
        text = text.replace("{{" + key + "}}", value)
    return text
