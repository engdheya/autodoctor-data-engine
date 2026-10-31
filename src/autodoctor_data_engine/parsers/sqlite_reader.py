"""Read-only SQLite reader used for sources that ship a compiled database."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any


class SqliteSourceError(RuntimeError):
    pass


def connect_readonly(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    if not path.is_file():
        raise SqliteSourceError(f"sqlite database not found: {path}")
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def list_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows]


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]


def read_sqlite(
    path: str | Path, query: str, params: tuple[Any, ...] = ()
) -> Iterator[dict[str, Any]]:
    conn = connect_readonly(path)
    try:
        for row in conn.execute(query, params):
            yield dict(row)
    finally:
        conn.close()
