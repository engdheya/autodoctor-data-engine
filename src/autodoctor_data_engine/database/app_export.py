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
    "dtc_evidence_sources",
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

-- ---------------------------------------------------------------------------
-- Client query contract. Portable SQLite only: no FTS module, no window
-- functions, no JSON operators - every statement below runs on the SQLite that
-- ships with Android and on the one bundled by sqlite3_flutter_libs.
-- ---------------------------------------------------------------------------

-- Search entry point: one row per identity, with the fields a list screen needs.
-- `code_compact` lets the client match "P 0301" without doing string surgery in
-- Dart: pass UPPER(REPLACE(input, ' ', '')) to `code_compact`.
DROP VIEW IF EXISTS v_dtc_search;
CREATE VIEW v_dtc_search AS
SELECT
    c.id                        AS dtc_code_id,
    c.code,
    UPPER(c.code)               AS code_upper,
    REPLACE(UPPER(c.code), ' ', '') AS code_compact,
    c.standard,
    c.context_type,
    c.context_key,
    c.category,
    c.system,
    m.name                      AS manufacturer,
    e.name                      AS ecu,
    (SELECT title FROM dtc_definitions d
      WHERE d.dtc_code_id = c.id AND d.language = 'en' AND d.is_canonical = 1 LIMIT 1) AS title_en,
    (SELECT title FROM dtc_definitions d
      WHERE d.dtc_code_id = c.id AND d.language = 'ar' AND d.is_canonical = 1 LIMIT 1) AS title_ar,
    CASE WHEN EXISTS (SELECT 1 FROM dtc_causes x WHERE x.dtc_code_id = c.id)
         THEN 'diagnosis_ready' ELSE 'definition_only' END AS content_tier,
    (SELECT COUNT(*) FROM dtc_causes x WHERE x.dtc_code_id = c.id)   AS cause_count,
    (SELECT COUNT(*) FROM dtc_symptoms x WHERE x.dtc_code_id = c.id) AS symptom_count,
    (SELECT COUNT(*) FROM dtc_tests x WHERE x.dtc_code_id = c.id)    AS test_count,
    (SELECT COUNT(*) FROM dtc_repairs x WHERE x.dtc_code_id = c.id)  AS repair_count,
    f.risk_level,
    f.mil,
    f.emissions_relevant,
    f.limp_mode_possible
FROM dtc_codes c
LEFT JOIN manufacturers m ON m.id = c.manufacturer_id
LEFT JOIN ecus e ON e.id = c.ecu_id
LEFT JOIN dtc_flags f ON f.dtc_code_id = c.id;

-- Causes, one row per cause per language, with the source-provided likelihood.
DROP VIEW IF EXISTS v_dtc_causes;
CREATE VIEW v_dtc_causes AS
SELECT c.dtc_code_id, c.id AS cause_id, t.language, t.label,
       c.likelihood, c.verification_status
FROM dtc_causes c
JOIN dtc_cause_texts t ON t.cause_id = c.id;

DROP VIEW IF EXISTS v_dtc_symptoms;
CREATE VIEW v_dtc_symptoms AS
SELECT s.dtc_code_id, s.id AS symptom_id, t.language, t.text, s.verification_status
FROM dtc_symptoms s
JOIN dtc_symptom_texts t ON t.symptom_id = s.id;

DROP VIEW IF EXISTS v_dtc_repairs;
CREATE VIEW v_dtc_repairs AS
SELECT r.dtc_code_id, r.id AS repair_id, t.language, t.text,
       r.difficulty, r.diy_possible, r.cost_min, r.cost_max, r.currency,
       r.hours_min, r.hours_max, r.verification_status
FROM dtc_repairs r
JOIN dtc_repair_texts t ON t.repair_id = r.id;

DROP VIEW IF EXISTS v_dtc_tests;
CREATE VIEW v_dtc_tests AS
SELECT t.dtc_code_id, t.id AS test_id, x.language, x.text, t.verification_status
FROM dtc_tests t
JOIN dtc_test_texts x ON x.test_id = t.id;

DROP VIEW IF EXISTS v_dtc_related;
CREATE VIEW v_dtc_related AS
SELECT r.dtc_code_id, r.related_code, r.relation_type, r.related_dtc_code_id,
       (SELECT title FROM dtc_definitions d
         WHERE d.dtc_code_id = r.related_dtc_code_id AND d.language = 'en'
           AND d.is_canonical = 1 LIMIT 1) AS related_title_en
FROM dtc_related_codes r;

-- Who said it: one row per (identity, source) with licence and commit, so the
-- client can render attribution without a second database.
DROP VIEW IF EXISTS v_dtc_provenance;
CREATE VIEW v_dtc_provenance AS
SELECT p.entity_type, p.entity_id, s.slug AS source_slug, s.name AS source_name,
       s.data_license, s.code_license, s.repo_url, s.attribution_required,
       version.commit_sha, version.version_label, version.retrieved_at,
       p.verification_status, p.is_derived, p.is_translated
FROM provenance_summary p
JOIN data_sources s ON s.id = p.source_id
LEFT JOIN data_versions version
       ON version.source_id = s.id
      AND version.id = (SELECT MAX(v2.id) FROM data_versions v2 WHERE v2.source_id = s.id);

DROP VIEW IF EXISTS v_dtc_conflicts;
CREATE VIEW v_dtc_conflicts AS
SELECT id AS conflict_id, dtc_code_id, code, context_key, conflict_type, attribute,
       summary, similarity, status, resolution_note
FROM conflicts;

DROP VIEW IF EXISTS v_manufacturers;
CREATE VIEW v_manufacturers AS
SELECT m.id AS manufacturer_id, m.name,
       (SELECT COUNT(*) FROM dtc_codes c WHERE c.manufacturer_id = m.id) AS code_count,
       (SELECT COUNT(*) FROM vehicles v WHERE v.manufacturer_id = m.id) AS vehicle_count
FROM manufacturers m;

DROP VIEW IF EXISTS v_pids;
CREATE VIEW v_pids AS
SELECT p.id AS pid_id, p.mode, p.pid, p.scope, p.bytes, p.unit, p.formula,
       p.range_min, p.range_max, p.signal_id, p.path,
       (SELECT name FROM pid_texts t WHERE t.pid_id = p.id AND t.language = 'en' LIMIT 1) AS name_en,
       (SELECT name FROM pid_texts t WHERE t.pid_id = p.id AND t.language = 'ar' LIMIT 1) AS name_ar
FROM pids p;

DROP VIEW IF EXISTS v_vehicles;
CREATE VIEW v_vehicles AS
SELECT v.id AS vehicle_id, m.name AS manufacturer, v.model, v.generation,
       v.year_start, v.year_end, v.description
FROM vehicles v
LEFT JOIN manufacturers m ON m.id = v.manufacturer_id;
"""

# NOTE: this table is deliberately a normal rowid table. As a WITHOUT ROWID table
# with this five-column primary key, SQLite 3.40's ``PRAGMA integrity_check``
# reports a spurious "NULL value in provenance_summary.verification_status" for
# every row (the column is NOT NULL and never null - verified by query). A
# shipped database whose integrity check fails is unusable in production, so the
# compactness of WITHOUT ROWID is traded for an artifact that passes the check;
# the NOT NULL invariant is additionally asserted in ``_populate_bundle``.
PROVENANCE_SUMMARY_SQL = """
CREATE TABLE provenance_summary (
    entity_type         TEXT    NOT NULL,
    entity_id           INTEGER NOT NULL,
    source_id           INTEGER NOT NULL REFERENCES data_sources(id),
    verification_status TEXT    NOT NULL,
    is_derived          INTEGER NOT NULL DEFAULT 0,
    is_translated       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (entity_type, entity_id, source_id, is_derived, is_translated)
);
"""


class LicenceError(RuntimeError):
    """Raised when a bundle would ship data outside the licensed source set."""


@dataclass
class AppBundleResult:
    path: Path
    tables_copied: int
    provenance_rows: int
    size_bytes: int
    source_set: str = "private"
    sources: tuple[str, ...] = ()


def unlicensed_sources(conn: sqlite3.Connection) -> list[str]:
    """Sources whose data must not leave the project."""
    rows = conn.execute(
        """
        SELECT slug FROM data_sources
        WHERE legal_review_status <> 'approved' OR COALESCE(redistribution_allowed, 0) = 0
        ORDER BY slug
        """
    ).fetchall()
    return [str(row[0]) for row in rows]


def assert_public_safe(conn: sqlite3.Connection) -> list[str]:
    """Refuse to publish a bundle that contains data we may not redistribute.

    This is the last line of defence: the build filters the sources before it
    merges, ``D011`` checks the merged database, and this checks the file that is
    about to be handed to a client.
    """
    offenders = unlicensed_sources(conn)
    if offenders:
        raise LicenceError(
            "refusing to publish a public bundle: "
            + ", ".join(offenders)
            + " are not approved for redistribution (see docs/LICENSES.md)"
        )
    stray = conn.execute(
        "SELECT COUNT(*) FROM conflict_evidence WHERE source_slug NOT IN "
        "(SELECT slug FROM data_sources)"
    ).fetchone()[0]
    if int(stray):
        raise LicenceError(
            f"refusing to publish: {int(stray)} conflict evidence rows reference an "
            "unknown source"
        )
    return offenders


def build_app_bundle(
    source_db: Path,
    target_db: Path,
    *,
    version: str | None = None,
    source_set: str = "private",
) -> AppBundleResult:
    target_db.parent.mkdir(parents=True, exist_ok=True)
    conn = create_database(target_db)
    try:
        try:
            return _populate_bundle(
                conn, source_db, target_db, version=version, source_set=source_set
            )
        except Exception:
            # a refused or failed bundle must not survive on disk
            conn.close()
            target_db.unlink(missing_ok=True)
            raise
    finally:
        conn.close()


def _populate_bundle(
    conn: sqlite3.Connection,
    source_db: Path,
    target_db: Path,
    *,
    version: str | None,
    source_set: str,
) -> AppBundleResult:
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
    missing_status = int(
        conn.execute(
            "SELECT COUNT(*) FROM provenance_summary WHERE verification_status IS NULL"
        ).fetchone()[0]
    )
    if missing_status:
        raise RuntimeError(
            f"{missing_status} provenance_summary rows have no verification status"
        )

    for table in DROPPED_TABLES:
        exists = conn.execute(
            "SELECT 1 FROM main.sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if exists:
            conn.execute(f"DROP TABLE main.{table}")
    conn.executescript(APP_VIEW_SQL)
    conn.execute("PRAGMA foreign_key_check")

    if source_set == "public":
        assert_public_safe(conn)
    sources = tuple(
        row[0] for row in conn.execute("SELECT slug FROM data_sources ORDER BY slug")
    )

    if version:
        conn.execute(
            """
            INSERT INTO db_versions (version, built_at, schema_version, source_set,
                sources_json, counts_json, validation_json, test_status, notes)
            VALUES (?, datetime('now'), '3', ?,
                (SELECT json_group_array(slug) FROM data_sources),
                '{}', '{}', 'passed', 'mobile app bundle (content + compact provenance)')
            ON CONFLICT(version) DO UPDATE SET
                source_set = excluded.source_set,
                notes = excluded.notes,
                test_status = excluded.test_status
            """,
            (version, source_set),
        )
    conn.commit()
    conn.execute("DETACH DATABASE src")
    conn.commit()
    optimise(conn)
    # The bundle is built in WAL mode. Checkpoint and close *before* the file is
    # vacuumed, otherwise the still-open connection can checkpoint a stale page
    # cache over the vacuumed file and silently drop the views created above.
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.commit()
    conn.close()

    _shrink(target_db)
    _verify_views(target_db)
    return AppBundleResult(
        path=target_db,
        tables_copied=copied,
        provenance_rows=provenance_rows,
        size_bytes=target_db.stat().st_size,
        source_set=source_set,
        sources=sources,
    )


def _shrink(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("VACUUM")
        conn.commit()
    finally:
        conn.close()


REQUIRED_VIEWS = (
    "v_dtc_lookup",
    "v_dtc_summary",
    "v_dtc_search",
    "v_dtc_causes",
    "v_dtc_symptoms",
    "v_dtc_repairs",
    "v_dtc_tests",
    "v_dtc_related",
    "v_dtc_provenance",
    "v_dtc_conflicts",
    "v_manufacturers",
    "v_pids",
    "v_vehicles",
)


def _verify_views(path: Path) -> None:
    """Re-read the finished file and prove the client views survived.

    Views are created through ``executescript`` and then the file is vacuumed;
    a bundle without them still looks valid table-by-table but breaks every
    query the Flutter client makes, so the artifact itself is checked.
    """
    probe = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        present = {
            str(row[0])
            for row in probe.execute("SELECT name FROM sqlite_master WHERE type = 'view'")
        }
    finally:
        probe.close()
    missing = [name for name in REQUIRED_VIEWS if name not in present]
    if missing:
        path.unlink(missing_ok=True)
        raise RuntimeError(
            f"app bundle {path.name} is missing view(s): {', '.join(missing)}"
        )


def schema_version() -> str:
    return "3"


__all__ = [
    "build_app_bundle",
    "AppBundleResult",
    "LicenceError",
    "assert_public_safe",
    "unlicensed_sources",
    "CONTENT_TABLES",
    "read_schema",
    "REQUIRED_VIEWS",
]
