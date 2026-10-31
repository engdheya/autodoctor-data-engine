"""Schema loading and connection helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class SchemaError(RuntimeError):
    pass


def read_schema(schema_path: str | Path | None = None) -> str:
    path = Path(schema_path) if schema_path else _default_schema_path()
    if not path.is_file():
        raise SchemaError(f"schema file not found: {path}")
    return path.read_text(encoding="utf-8")


def _default_schema_path() -> Path:
    package_dir = Path(__file__).resolve()
    # src/autodoctor_data_engine/database/connection.py -> project root
    for parent in package_dir.parents:
        candidate = parent / "db" / "schema.sql"
        if candidate.is_file():
            return candidate
    raise SchemaError("db/schema.sql not found relative to the package")


def connect(path: str | Path, *, readonly: bool = False) -> sqlite3.Connection:
    path = Path(path)
    if readonly:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if not readonly:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def create_database(path: str | Path, schema_path: str | Path | None = None) -> sqlite3.Connection:
    """Create an empty database with the full schema applied."""
    path = Path(path)
    if path.exists():
        path.unlink()
    for suffix in ("-wal", "-shm"):
        extra = Path(str(path) + suffix)
        if extra.exists():
            extra.unlink()
    conn = connect(path)
    conn.executescript(read_schema(schema_path))
    conn.commit()
    return conn


def optimise(conn: sqlite3.Connection) -> None:
    """Apply the settings we want baked into a shipped database."""
    conn.executescript(
        """
        PRAGMA journal_mode = DELETE;
        PRAGMA optimize;
        ANALYZE;
        VACUUM;
        """
    )
    conn.commit()
