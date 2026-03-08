"""Shared CLI helpers."""

from __future__ import annotations

import json
from pathlib import Path


def load_json_input(value: str) -> dict:
    """Parse a --json argument.

    Accepts:
      - Inline JSON string:  '{"name": "Acme"}'
      - File reference:      @./config.json  or  @/abs/path.json
    """
    if value.startswith("@"):
        path = Path(value[1:]).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"JSON file not found: {path}")
        return json.loads(path.read_text())
    return json.loads(value)
