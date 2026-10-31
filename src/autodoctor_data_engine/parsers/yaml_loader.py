"""YAML reader with strict error reporting.

Upstream YAML is often hand-edited, so a malformed file must fail loudly with the
file name instead of silently dropping records.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class YamlParseError(RuntimeError):
    def __init__(self, path: str | Path, reason: str):
        super().__init__(f"{path}: {reason}")
        self.path = Path(path)
        self.reason = reason


def load_yaml(path: str | Path) -> Any:
    path = Path(path)
    try:
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise YamlParseError(path, str(exc)) from exc


def load_yaml_all(path: str | Path) -> list[Any]:
    """Load a multi-document YAML file."""
    path = Path(path)
    try:
        with open(path, encoding="utf-8") as fh:
            return list(yaml.safe_load_all(fh))
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise YamlParseError(path, str(exc)) from exc
