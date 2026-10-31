"""SQLite access layer.

Imports are lazy on purpose: ``merger.loader`` depends on ``database.repository``,
while ``database.build`` depends on the merger, so an eager import of
``database.build`` here would create a cycle when a caller imports a submodule
first (``import autodoctor_data_engine.merger.loader``).
"""

from __future__ import annotations

from typing import Any

from .connection import connect, create_database, read_schema
from .repository import Repository

__all__ = [
    "connect",
    "create_database",
    "read_schema",
    "Repository",
    "build_database",
    "BuildResult",
]


def __getattr__(name: str) -> Any:  # pragma: no cover - trivial indirection
    if name in {"build_database", "BuildResult"}:
        from . import build as build_module

        return getattr(build_module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
