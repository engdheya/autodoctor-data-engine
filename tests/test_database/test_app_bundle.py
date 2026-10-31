"""The Flutter bundle must be self-contained, small and licence-aware."""

from __future__ import annotations

import json

from autodoctor_data_engine.database.connection import connect


def test_app_bundle_exists_and_is_smaller(built) -> None:
    assert built.app_bundle_path and built.app_bundle_path.is_file()
    assert built.app_bundle_bytes > 0
    assert built.app_bundle_bytes < built.export_path.stat().st_size


def test_app_bundle_keeps_content_and_drops_the_claim_matrix(built) -> None:
    conn = connect(built.app_bundle_path, readonly=True)
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert "provenance_claims" not in tables
        assert "source_records" not in tables
        assert "validation_results" not in tables
        assert {"dtc_codes", "dtc_definitions", "dtc_causes", "provenance_summary",
                "conflicts", "pids"} <= tables

        codes = conn.execute("SELECT COUNT(*) FROM dtc_codes").fetchone()[0]
        provenance = conn.execute("SELECT COUNT(*) FROM provenance_summary").fetchone()[0]
        assert codes > 0 and provenance > 0
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_app_bundle_can_answer_a_diagnostic_card(built) -> None:
    conn = connect(built.app_bundle_path, readonly=True)
    try:
        row = conn.execute(
            """
            SELECT * FROM v_dtc_summary
            WHERE code = 'P0301' AND context_type = 'generic'
            """
        ).fetchone()
        assert row["title_en"] == "Cylinder 1 Misfire Detected"
        assert row["title_ar"], "the reviewed Arabic translation must be included"
        assert row["cause_count"] >= 2
        assert row["symptom_count"] == 2
        assert row["repair_count"] == 1
        assert row["source_count"] >= 2
        assert row["risk_level"] == "high"
        assert row["mil"] == 1

        # a client can always resolve who said what, including the licence
        sources = conn.execute(
            """
            SELECT s.slug, s.data_license, s.repo_url, v.commit_sha
            FROM provenance_summary p
            JOIN data_sources s ON s.id = p.source_id
            JOIN data_versions v ON v.source_id = s.id
            WHERE p.entity_type = 'dtc_code' AND p.entity_id = ?
            """,
            (row["dtc_code_id"],),
        ).fetchall()
        assert {source["slug"] for source in sources} >= {"obdex", "wal33d"}
        assert all(source["data_license"] for source in sources)
    finally:
        conn.close()


def test_manifest_records_the_app_bundle(built) -> None:
    manifest = json.loads(built.manifest_path.read_text(encoding="utf-8"))
    bundle = manifest["app_bundle"]
    assert bundle["file"].endswith(".sqlite")
    assert bundle["sha256"]
    assert bundle["bytes"] == built.app_bundle_bytes
