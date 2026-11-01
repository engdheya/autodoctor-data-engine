"""Gate D012: an unreviewed critical conflict must stop a release."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

from autodoctor_data_engine.conflict_resolution.triage import (
    review_batch,
    triage_conflicts,
    unreviewed_critical_count,
)
from autodoctor_data_engine.validators.database_rules import (
    failed_blocking,
    run_database_checks,
)


def _insert_critical_conflict(conn: sqlite3.Connection, similarity: float = 0.2) -> str:
    row = conn.execute(
        """
        SELECT c.id, c.code, c.context_key FROM dtc_codes c
        JOIN dtc_flags f ON f.dtc_code_id = c.id
        WHERE c.context_type = 'generic' AND f.risk_level IN ('high', 'critical')
        LIMIT 1
        """
    ).fetchone()
    fingerprint = f"gate{int(similarity * 100):03d}fingerprint"
    conn.execute(
        """
        INSERT INTO conflicts (fingerprint, conflict_type, entity_type, entity_id,
            dtc_code_id, code, context_key, attribute, summary, similarity, status, created_at)
        VALUES (?, 'definition_disagreement', 'dtc_code', ?, ?, ?, ?, 'definition',
                'synthetic conflict for the gate test', ?, 'needs_review', '2026-11-01T00:00:00Z')
        """,
        (fingerprint, row[0], row[0], row[1], row[2], similarity),
    )
    conn.execute(
        """
        INSERT INTO conflict_evidence (conflict_id, claim_id, source_slug, value_text)
        VALUES ((SELECT id FROM conflicts WHERE fingerprint = ?), NULL, 'obdex', 'statement A')
        """,
        (fingerprint,),
    )
    conn.commit()
    return fingerprint


def _copy(built, tmp_path: Path) -> sqlite3.Connection:
    target = tmp_path / "gate.sqlite"
    shutil.copy(built.database_path, target)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_gate_blocks_when_a_critical_conflict_is_unreviewed(built, tmp_path: Path) -> None:
    conn = _copy(built, tmp_path)
    try:
        _insert_critical_conflict(conn)
        checks = run_database_checks(conn, source_set="public")
        gate = next(c for c in checks if c.check_id == "D012_critical_conflicts")
        assert gate.blocking and not gate.passed
        assert gate.count >= 1
        assert "unreviewed critical conflict" in gate.detail
        assert gate in failed_blocking(checks)
    finally:
        conn.close()


def test_gate_passes_when_the_conflict_is_accepted_by_a_human(built, tmp_path: Path) -> None:
    conn = _copy(built, tmp_path)
    try:
        _insert_critical_conflict(conn)
        conn.execute(
            "UPDATE conflicts SET status = 'accepted_difference', resolution_note = ? "
            "WHERE fingerprint LIKE 'gate%'",
            ("reviewer: qa-lead - both statements describe the same circuit",),
        )
        conn.commit()
        checks = run_database_checks(conn, source_set="public")
        gate = next(c for c in checks if c.check_id == "D012_critical_conflicts")
        assert gate.passed and gate.count == 0
    finally:
        conn.close()


def test_override_is_recorded_not_silent(built, tmp_path: Path) -> None:
    conn = _copy(built, tmp_path)
    try:
        _insert_critical_conflict(conn)
        checks = run_database_checks(
            conn,
            source_set="public",
            allow_critical_conflicts="internal review build",
            override_reviewer="qa-lead",
        )
        gate = next(c for c in checks if c.check_id == "D012_critical_conflicts")
        assert gate.passed
        assert "OVERRIDDEN by qa-lead" in gate.detail
        assert "internal review build" in gate.detail
    finally:
        conn.close()


def test_sql_gate_and_python_band_agree(built, tmp_path: Path) -> None:
    """The gate uses SQL, the report uses Python; they must count the same rows."""
    conn = _copy(built, tmp_path)
    try:
        _insert_critical_conflict(conn, similarity=0.1)
        _insert_critical_conflict(conn, similarity=0.6)
        report = triage_conflicts(conn)
        critical = report["totals"]["by_band"]["critical"]
        assert unreviewed_critical_count(conn) == critical
        assert critical >= 2
    finally:
        conn.close()


def test_review_batch_carries_evidence_and_changes_nothing(built, tmp_path: Path) -> None:
    conn = _copy(built, tmp_path)
    try:
        _insert_critical_conflict(conn, similarity=0.15)
        before = conn.execute("SELECT status, resolution_note FROM conflicts ORDER BY id").fetchall()
        batch = review_batch(conn, band="critical", limit=10)
        after = conn.execute("SELECT status, resolution_note FROM conflicts ORDER BY id").fetchall()
        assert [tuple(r) for r in before] == [tuple(r) for r in after]
        assert batch["conflicts"], "the synthetic critical conflict must appear in the batch"
        entry = batch["conflicts"][0]
        assert entry["fingerprint"]
        assert entry["statements"] and entry["statements"][0]["source"]
        assert entry["decision"]["command"].startswith("autodoctor review-conflict")
        assert "not a decision" in batch["reviewer_note"]
    finally:
        conn.close()


def test_override_is_recorded_in_the_manifest(imported) -> None:
    from autodoctor_data_engine.database.build import build_database

    result = build_database(
        imported,
        version="0.1.1",
        allow_critical_conflicts="RC published for integration testing only",
        override_reviewer="data-engineering",
    )
    assert result.manifest_path is not None
    manifest = json.loads(Path(result.manifest_path).read_text())
    assert manifest["gate_overrides"] == [
        {
            "gate": "D012_critical_conflicts",
            "reason": "RC published for integration testing only",
            "reviewer": "data-engineering",
        }
    ]
    assert manifest["notes"].startswith("D012_critical_conflicts overridden")
    assert any("D012 overridden" in w for w in manifest["warnings"])
