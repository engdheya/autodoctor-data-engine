"""JSON reader with contextual error messages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonParseError(RuntimeError):
    def __init__(self, path: str | Path, reason: str):
        super().__init__(f"{path}: {reason}")
        self.path = Path(path)
        self.reason = reason


def load_json(path: str | Path) -> Any:
    path = Path(path)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise JsonParseError(path, str(exc)) from exc
