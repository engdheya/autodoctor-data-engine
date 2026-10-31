"""The unified database: identity, provenance, conflicts, gates and releases."""

from __future__ import annotations

import json

from helpers import create_project

from autodoctor_data_engine.config import Settings
from autodoctor_data_engine.database.build import build_database
from autodoctor_data_engine.database.connection import connect
from autodoctor_data_engine.pipeline import import_source
from autodoctor_data_engine.utils.hashing import sha256_file


def test_build_publishes_a_release(built) -> None:
    assert built.test_status == "passed"
    assert built.export_path and built.export_path.is_file()
    assert built.manifest_path and built.manifest_path.is_file()
    assert built.counts["dtc_codes"] > 0


def test_code_alone_is_not_the_identity(built, db_conn) -> None:
    rows = db_conn.execute(
        "SELECT context_key, manufacturer_id FROM dtc_codes WHERE code = 'P1690' ORDER BY id"
    ).fetchall()
    assert len(rows) == 2
    assert len({row["context_key"] for row in rows}) == 2

    p0301 = db_conn.execute(
        "SELECT COUNT(*) FROM dtc_codes WHERE code = 'P0301'"
    ).fetchone()[0]
    assert p0301 == 1


def test_every_dtc_has_a_definition_and_a_claim(db_conn) -> None:
    missing_definition = db_conn.execute(
        """
        SELECT COUNT(*) FROM dtc_codes c
        WHERE NOT EXISTS (SELECT 1 FROM dtc_definitions d WHERE d.dtc_code_id = c.id)
        """
    ).fetchone()[0]
    assert missing_definition == 0

    missing_claim = db_conn.execute(
        """
        SELECT COUNT(*) FROM dtc_codes c
        WHERE NOT EXISTS (
            SELECT 1 FROM provenance_claims p
            WHERE p.entity_type = 'dtc_code' AND p.entity_id = c.id
        )
        """
    ).fetchone()[0]
    assert missing_claim == 0


def test_definition_carries_multiple_sources(db_conn) -> None:
    rows = db_conn.execute(
        """
        SELECT d.id, d.title, d.verification_status FROM dtc_codes c
        JOIN dtc_definitions d ON d.dtc_code_id = c.id
        WHERE c.code = 'P0301' AND d.language = 'en'
        """
    ).fetchall()
    assert len(rows) >= 2, "OBDex adds a long description, the others a bare title"

    sources: set[str] = set()
    per_definition: dict[int, set[str]] = {}
    for row in rows:
        claims = {
            claim[0]
            for claim in db_conn.execute(
                """
                SELECT s.slug FROM provenance_claims p
                JOIN data_sources s ON s.id = p.source_id
                WHERE p.entity_type = 'dtc_definition' AND p.entity_id = ?
                """,
                (row["id"],),
            )
        }
        per_definition[row["id"]] = claims
        sources |= claims

    assert {"obdex", "wal33d", "autodiag"} <= sources
    assert any(len(claim_sources) >= 2 for claim_sources in per_definition.values())


def test_corroborated_definition_is_marked_verified(db_conn) -> None:
    statuses = {
        row[0]
        for row in db_conn.execute(
            """
            SELECT d.verification_status FROM dtc_codes c
            JOIN dtc_definitions d ON d.dtc_code_id = c.id
            WHERE c.code = 'P0301' AND d.language = 'en'
            """
        )
    }
    # the statement three sources agree on is corroborated, including the richer
    # OBDex elaboration whose headline matches the shorter Wal33D wording
    assert statuses == {"verified"}

    # a statement only one lineage reports stays source-reported
    sole = {
        row[0]
        for row in db_conn.execute(
            """
            SELECT d.verification_status FROM dtc_codes c
            JOIN dtc_definitions d ON d.dtc_code_id = c.id
            WHERE c.code = 'P1690' AND d.language = 'en'
            """
        )
    }
    assert sole == {"source_reported"}


def test_conflicting_definitions_are_kept_and_flagged(built, db_conn) -> None:
    conflict = db_conn.execute(
        "SELECT * FROM conflicts WHERE code = 'P0420' AND conflict_type = 'definition_disagreement'"
    ).fetchone()
    assert conflict is not None
    assert conflict["status"] == "needs_review"

    # both statements survive, and both are marked conflicting
    definitions = db_conn.execute(
        """
        SELECT d.title, d.verification_status FROM dtc_codes c
        JOIN dtc_definitions d ON d.dtc_code_id = c.id
        WHERE c.code = 'P0420'
        """
    ).fetchall()
    assert len(definitions) >= 2
    assert any(d["verification_status"] == "conflicting" for d in definitions)
    titles = {d["title"] for d in definitions}
    assert "Catalyst System Efficiency Below Threshold (Bank 1)" in titles
    assert "Catalyst Monitor Circuit High Input" in titles


def test_conflict_evidence_names_the_sources(db_conn) -> None:
    rows = db_conn.execute(
        """
        SELECT e.source_slug, e.value_text FROM conflicts c
        JOIN conflict_evidence e ON e.conflict_id = c.id
        WHERE c.code = 'P0420'
        """
    ).fetchall()
    assert {row["source_slug"] for row in rows} >= {"obdex", "autodiag"}
    assert all(row["value_text"] for row in rows)


def test_canonical_definition_prefers_the_rich_source(db_conn) -> None:
    titles = db_conn.execute(
        """
        SELECT d.title, d.is_canonical FROM dtc_codes c
        JOIN dtc_definitions d ON d.dtc_code_id = c.id
        WHERE c.code = 'P0100' AND d.language = 'en' ORDER BY d.id
        """
    ).fetchall()
    canonical = [row["title"] for row in titles if row["is_canonical"]]
    assert canonical == ["Mass or Volume Air Flow Circuit Malfunction"]


def test_risk_is_derived_with_a_rule_id(db_conn) -> None:
    row = db_conn.execute(
        """
        SELECT f.risk_level, f.risk_rule_id, f.risk_basis_json FROM dtc_codes c
        JOIN dtc_flags f ON f.dtc_code_id = c.id WHERE c.code = 'P0301'
        """
    ).fetchone()
    assert row["risk_level"] == "high"
    assert row["risk_rule_id"] == "risk_flags_v1"
    basis = json.loads(row["risk_basis_json"])
    assert basis["score"] == 4

    derived = db_conn.execute(
        """
        SELECT COUNT(*) FROM provenance_claims
        WHERE entity_type = 'dtc_flags' AND attribute = 'risk_level' AND is_derived = 1
        """
    ).fetchone()[0]
    assert derived >= 1


def test_vehicles_and_parameters_from_obdb(db_conn) -> None:
    vehicles = db_conn.execute("SELECT model, generation, year_start FROM vehicles").fetchall()
    assert ("Camry", "Fifth Generation (XV30)", 2001) in [tuple(v) for v in vehicles]

    parameters = db_conn.execute(
        "SELECT mode, pid, signal_id, unit FROM pids WHERE scope = 'vehicle'"
    ).fetchall()
    assert len(parameters) == 2
    assert ("22", "0103", "CAMRY_ENG_ODO", "kilometers") in [tuple(p) for p in parameters]

    generic = db_conn.execute("SELECT COUNT(*) FROM pids WHERE scope = 'generic'").fetchone()[0]
    assert generic == 2


def test_related_codes_are_reachable(db_conn) -> None:
    related = db_conn.execute(
        """
        SELECT r.related_code FROM dtc_codes c
        JOIN dtc_related_codes r ON r.dtc_code_id = c.id
        WHERE c.code = 'P0301' ORDER BY r.related_code
        """
    ).fetchall()
    assert [row[0] for row in related] == ["P0300", "P0302", "P0304"]


def test_duplicate_groups_and_context_variants_are_stored(db_conn) -> None:
    exact = db_conn.execute(
        "SELECT COUNT(*) FROM duplicate_groups WHERE match_type = 'exact_statement'"
    ).fetchone()[0]
    assert exact >= 1
    variants = db_conn.execute(
        "SELECT COUNT(*) FROM duplicate_groups WHERE match_type = 'code_context_variants'"
    ).fetchone()[0]
    assert variants >= 1

    members = db_conn.execute(
        """
        SELECT g.group_key, m.entity_type, m.entity_ref FROM duplicate_groups g
        JOIN duplicate_members m ON m.group_id = g.id
        WHERE g.match_type = 'code_context_variants'
        """
    ).fetchall()
    assert members
    assert all(row["entity_ref"].startswith("P1690|") for row in members)


def test_manifest_matches_the_export(built) -> None:
    manifest = json.loads(built.manifest_path.read_text(encoding="utf-8"))
    assert manifest["version"] == "0.1.0"
    assert manifest["test_status"] == "passed"
    assert manifest["database_sha256"] == sha256_file(built.export_path)
    assert manifest["database_bytes"] == built.export_path.stat().st_size
    assert {s["slug"] for s in manifest["sources"]} == {"obdex", "wal33d", "autodiag", "obdb"}
    for source in manifest["sources"]:
        assert "data_license" in source and "legal_review" in source
    assert manifest["app_bundle"]["sha256"]
    assert manifest["validation"]["rejected_records"] == 0


def test_db_versions_records_the_release(built) -> None:
    conn = connect(built.database_path, readonly=True)
    try:
        row = conn.execute("SELECT * FROM db_versions WHERE version = '0.1.0'").fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["test_status"] == "passed"
    assert row["published_at"]
    assert json.loads(row["counts_json"])["dtc_codes"] > 0


def test_schema_has_no_unexpected_gaps(built) -> None:
    conn = connect(built.database_path, readonly=True)
    try:
        checks = conn.execute("PRAGMA foreign_key_check").fetchall()
        assert checks == []
        for table in ("dtc_codes", "dtc_definitions", "provenance_claims", "data_sources"):
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert count > 0
    finally:
        conn.close()


def test_release_is_blocked_when_validation_fails(tmp_path) -> None:
    root = create_project(tmp_path / "blocked")
    settings = Settings(root=root)
    bad_file = settings.sources["autodiag"].local_path / "data-src" / "ecu" / "generic" / "audi" / "codes" / "P15O9.yml"
    bad_file.write_text(
        "code: P15O9\ndefinition: Typo in a code\nstandard: [saej2012.2002]\n"
        "protocol: [obd2]\nevidence: [obdcodex]\n",
        encoding="utf-8",
    )
    for slug in ("obdex", "wal33d", "autodiag"):
        import_source(settings, slug)

    blocked = build_database(settings, version="9.9.9", strict=True)
    assert blocked.test_status == "failed"
    assert blocked.export_path is None
    assert not (settings.paths.exports / "autodoctor-9.9.9.sqlite").exists()
    assert any("quarantined" in w for w in blocked.warnings)

    # the quarantined record never reaches the database
    conn = connect(blocked.database_path, readonly=True)
    try:
        assert conn.execute("SELECT COUNT(*) FROM dtc_codes WHERE code='P15O9'").fetchone()[0] == 0
    finally:
        conn.close()

    allowed = build_database(settings, version="9.9.9", strict=False)
    assert allowed.test_status == "passed"
    assert allowed.export_path is not None


def test_second_build_increments_the_version_from_disk(imported: Settings) -> None:
    first = build_database(imported, version="1.0.0")
    assert first.test_status == "passed"
    second = build_database(imported, part="minor")
    assert second.version == "1.1.0"
    third = build_database(imported, part="patch")
    assert third.version == "1.1.1"
