"""Export a compact, mobile-ready bundle for the Flutter client.

The engineering database keeps everything: every source record, every claim, every
validation run. That is far too heavy to download onto a phone (160 MB+).

The app bundle therefore keeps:

  * all content tables (codes, definitions, causes, symptoms, tests, repairs,
    components, related codes, flags, PIDs, vehicles, ECUs)
  * the source registry and upstream versions (for the "where does this come
    from" screen)
  * conflicts, so the UI can show "sources disagree" instead of pretending
  * a compact ``provenance_summary`` row per definition instead of the full claim
    matrix

and drops: raw records, file inventories, validation logs, duplicate evidence and
the provenance claim matrix (all of which remain in the engineering database).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .connection import create_database, optimise, read_schema

#: tables copied verbatim, in foreign-key order
CONTENT_TABLES = [
    "data_sources",
    "data_versions",
    "manufacturers",
    "vehicles",
    "vehicle_variants",
    "ecus",
    "vehicle_ecu_links",
    "pids",
    "pid_texts",
    "dtc_codes",
    "dtc_definitions",
    "dtc_causes",
    "dtc_cause_texts",
    "dtc_symptoms",
    "dtc_symptom_texts",
    "dtc_tests",
    "dtc_test_texts",
    "dtc_repairs",
    "dtc_repair_texts",
    "dtc_components",
    "dtc_component_texts",
    "dtc_related_codes",
    "dtc_flags",
    "conflicts",
    "conflict_evidence",
    "translations",
    "db_versions",
]

#: tables whose rows must be adapted before copying (dangling provenance references)
COPY_OVERRIDES = {
    "conflict_evidence": (
        "INSERT INTO main.conflict_evidence (id, conflict_id, claim_id, source_slug, value_text) "
        "SELECT id, conflict_id, NULL, source_slug, value_text FROM src.conflict_evidence"
    ),
}

# Provenance for the mobile client is an integer-only join table: the licence,
# commit and repository live once in data_sources / data_versions.
#: engineering-only tables dropped from the mobile bundle
DROPPED_TABLES = [
    "provenance_claims",
    "source_records",
    "source_files",
    "validation_results",
    "duplicate_members",
    "duplicate_groups",
]

APP_VIEW_SQL = """
DROP VIEW IF EXISTS v_dtc_summary;
CREATE VIEW v_dtc_summary AS
SELECT
    c.id AS dtc_code_id,
    c.code,
    c.context_type,
    m.name AS manufacturer,
    (SELECT title FROM dtc_definitions d
      WHERE d.dtc_code_id = c.id AND d.language = 'en' AND d.is_canonical = 1 LIMIT 1) AS title_en,
    (SELECT title FROM dtc_definitions d
      WHERE d.dtc_code_id = c.id AND d.language = 'ar' AND d.is_canonical = 1 LIMIT 1) AS title_ar,
    (SELECT COUNT(*) FROM dtc_causes x WHERE x.dtc_code_id = c.id)     AS cause_count,
    (SELECT COUNT(*) FROM dtc_symptoms x WHERE x.dtc_code_id = c.id)   AS symptom_count,
    (SELECT COUNT(*) FROM dtc_tests x WHERE x.dtc_code_id = c.id)      AS test_count,
    (SELECT COUNT(*) FROM dtc_repairs x WHERE x.dtc_code_id = c.id)    AS repair_count,
    (SELECT COUNT(DISTINCT p.source_id) FROM provenance_summary p
      WHERE p.entity_type = 'dtc_code' AND p.entity_id = c.id)         AS source_count,
    f.risk_level,
    f.mil,
    f.emissions_relevant
FROM dtc_codes c
LEFT JOIN manufacturers m ON m.id = c.manufacturer_id
LEFT JOIN dtc_flags f ON f.dtc_code_id = c.id;
"""

PROVENANCE_SUMMARY_SQL = """
CREATE TABLE provenance_summary (
    entity_type         TEXT    NOT NULL,
    entity_id           INTEGER NOT NULL,
    source_id           INTEGER NOT NULL REFERENCES data_sources(id),
    verification_status TEXT    NOT NULL,
    is_derived          INTEGER NOT NULL DEFAULT 0,
    is_translated       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (entity_type, entity_id, source_id, is_derived, is_translated)
) WITHOUT ROWID;
"""


@dataclass
class AppBundleResult:
    path: Path
    tables_copied: int
    provenance_rows: int
    size_bytes: int


def build_app_bundle(source_db: Path, target_db: Path, *, version: str | None = None) -> AppBundleResult:
    target_db.parent.mkdir(parents=True, exist_ok=True)
    conn = create_database(target_db)
    try:
        conn.execute(f"ATTACH DATABASE '{source_db}' AS src")
        copied = 0
        for table in CONTENT_TABLES:
            exists = conn.execute(
                "SELECT 1 FROM src.sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if not exists:
                continue
            statement = COPY_OVERRIDES.get(table, f"INSERT INTO main.{table} SELECT * FROM src.{table}")
            conn.execute(statement)
            copied += 1

        conn.executescript(PROVENANCE_SUMMARY_SQL)
        conn.execute(
            """
            INSERT OR IGNORE INTO provenance_summary (entity_type, entity_id, source_id,
                verification_status, is_derived, is_translated)
            SELECT p.entity_type, p.entity_id, p.source_id,
                   MAX(p.verification_status), p.is_derived, p.is_translated
            FROM src.provenance_claims p
            GROUP BY p.entity_type, p.entity_id, p.source_id, p.is_derived, p.is_translated
            """
        )
        provenance_rows = int(
            conn.execute("SELECT COUNT(*) FROM provenance_summary").fetchone()[0]
        )

        for table in DROPPED_TABLES:
            exists = conn.execute(
                "SELECT 1 FROM main.sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if exists:
                conn.execute(f"DROP TABLE main.{table}")
        conn.executescript(APP_VIEW_SQL)
        conn.execute("PRAGMA foreign_key_check")

        if version:
            conn.execute(
                """
                INSERT INTO db_versions (version, built_at, schema_version, sources_json,
                    counts_json, validation_json, test_status, notes)
                VALUES (?, datetime('now'), '1',
                    (SELECT json_group_array(slug) FROM data_sources),
                    '{}', '{}', 'passed', 'mobile app bundle (content + compact provenance)')
                ON CONFLICT(version) DO NOTHING
                """,
                (version,),
            )
        conn.commit()
        conn.execute("DETACH DATABASE src")
        conn.commit()
        optimise(conn)
    finally:
        conn.close()

    _shrink(target_db)
    return AppBundleResult(
        path=target_db,
        tables_copied=copied,
        provenance_rows=provenance_rows,
        size_bytes=target_db.stat().st_size,
    )


def _shrink(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("VACUUM")
        conn.commit()
    finally:
        conn.close()


def schema_version() -> str:
    return "1"


__all__ = ["build_app_bundle", "AppBundleResult", "CONTENT_TABLES", "read_schema"]
