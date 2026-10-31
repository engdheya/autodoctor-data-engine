"""The queries the Flutter client is expected to run."""

from __future__ import annotations

import sqlite3

import pytest


def test_lookup_by_code_returns_every_context(db_conn) -> None:
    rows = db_conn.execute(
        "SELECT context_type, context_key FROM dtc_codes WHERE code = 'P1690' ORDER BY context_type"
    ).fetchall()
    assert {row["context_type"] for row in rows} == {"manufacturer"}
    assert len(rows) == 2


def test_filter_by_manufacturer(db_conn) -> None:
    rows = db_conn.execute(
        """
        SELECT c.code, d.title, m.name FROM dtc_codes c
        JOIN dtc_definitions d ON d.dtc_code_id = c.id AND d.is_canonical = 1
        JOIN manufacturers m ON m.id = c.manufacturer_id
        WHERE c.code = 'P1690' AND m.name = 'Ford'
        """
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["title"] == "Wastegate Solenoid Circuit Malfunction"


def test_filter_by_ecu(db_conn) -> None:
    rows = db_conn.execute(
        """
        SELECT c.code, e.name FROM dtc_codes c
        JOIN ecus e ON e.id = c.ecu_id
        WHERE e.name = 'Bosch EDC16C34'
        """
    ).fetchall()
    assert [row["code"] for row in rows] == ["P1113"]


def test_search_view_is_usable_by_a_client(db_conn) -> None:
    rows = db_conn.execute(
        """
        SELECT code, title, language, verification_status, manufacturer
        FROM v_dtc_lookup
        WHERE code = 'P0420' ORDER BY language, is_canonical DESC
        """
    ).fetchall()
    assert rows
    assert {row["language"] for row in rows} >= {"en"}
    assert all(row["title"] for row in rows)


def test_like_search_over_titles(db_conn) -> None:
    rows = db_conn.execute(
        """
        SELECT DISTINCT code FROM v_dtc_lookup
        WHERE title LIKE '%Misfire%' OR title LIKE '%misfire%'
        """
    ).fetchall()
    assert "P0301" in {row["code"] for row in rows}


def test_missing_code_returns_nothing(db_conn) -> None:
    assert db_conn.execute("SELECT * FROM dtc_codes WHERE code = 'P9999'").fetchall() == []


def test_indexes_exist_for_the_hot_paths(db_conn) -> None:
    indexes = {row[0] for row in db_conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index'"
    )}
    assert "idx_dtc_codes_code" in indexes
    assert "idx_dtc_codes_context" in indexes
    assert "idx_defs_lang" in indexes


def test_read_only_connection_is_enforced(built) -> None:
    from autodoctor_data_engine.database.connection import connect

    conn = connect(built.export_path, readonly=True)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM dtc_definitions")
    finally:
        conn.close()
