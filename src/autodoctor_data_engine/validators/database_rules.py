"""Post-merge checks executed directly against the built SQLite file.

These are release gates: if any ``blocking`` check fails the engine refuses to
publish the exported database.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class DatabaseCheck:
    check_id: str
    description: str
    blocking: bool
    passed: bool
    detail: str = ""
    count: int = 0


def _scalar(conn: sqlite3.Connection, query: str) -> int:
    row = conn.execute(query).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def run_database_checks(
    conn: sqlite3.Connection, *, source_set: str = "private"
) -> list[DatabaseCheck]:
    """Evaluate the release gates.

    ``source_set`` decides how strict the licence gate is: a private build may
    carry sources awaiting a legal review (warning), a public build may not
    (blocking), and a public build additionally has to prove that no row from a
    non-redistributable source survived the merge (``D011``).
    """
    public = source_set == "public"
    checks: list[DatabaseCheck] = []

    fk_problems = conn.execute("PRAGMA foreign_key_check").fetchall()
    checks.append(
        DatabaseCheck(
            "D001_foreign_keys",
            "PRAGMA foreign_key_check returns no rows",
            True,
            not fk_problems,
            f"{len(fk_problems)} violating rows",
            len(fk_problems),
        )
    )

    orphan_codes = _scalar(
        conn,
        """
        SELECT COUNT(*) FROM dtc_codes c
        WHERE NOT EXISTS (SELECT 1 FROM dtc_definitions d WHERE d.dtc_code_id = c.id)
        """,
    )
    checks.append(
        DatabaseCheck(
            "D002_codes_have_definitions",
            "every dtc_codes row has at least one definition",
            True,
            orphan_codes == 0,
            f"{orphan_codes} codes without definitions",
            orphan_codes,
        )
    )

    missing_provenance = _scalar(
        conn,
        """
        SELECT COUNT(*) FROM dtc_codes c
        WHERE NOT EXISTS (
            SELECT 1 FROM provenance_claims p
            WHERE p.entity_type = 'dtc_code' AND p.entity_id = c.id
        )
        """,
    )
    checks.append(
        DatabaseCheck(
            "D003_provenance_present",
            "every DTC has at least one provenance claim",
            True,
            missing_provenance == 0,
            f"{missing_provenance} DTCs without provenance",
            missing_provenance,
        )
    )

    duplicate_contexts = _scalar(
        conn,
        "SELECT COUNT(*) FROM (SELECT context_key FROM dtc_codes GROUP BY context_key HAVING COUNT(*) > 1)",
    )
    checks.append(
        DatabaseCheck(
            "D004_context_unique",
            "context_key is unique (code alone is not an identity)",
            True,
            duplicate_contexts == 0,
            f"{duplicate_contexts} duplicated context keys",
            duplicate_contexts,
        )
    )

    multi_canonical = _scalar(
        conn,
        """
        SELECT COUNT(*) FROM (
            SELECT dtc_code_id, language FROM dtc_definitions
            WHERE is_canonical = 1
            GROUP BY dtc_code_id, language HAVING COUNT(*) > 1
        )
        """,
    )
    checks.append(
        DatabaseCheck(
            "D005_single_canonical",
            "at most one canonical definition per (code, language)",
            True,
            multi_canonical == 0,
            f"{multi_canonical} (code, language) pairs with several canonicals",
            multi_canonical,
        )
    )

    dangling_related = _scalar(
        conn,
        """
        SELECT COUNT(*) FROM dtc_related_codes r
        WHERE r.related_code NOT IN (SELECT code FROM dtc_codes)
        """,
    )
    checks.append(
        DatabaseCheck(
            "D006_related_codes_resolvable",
            "related codes resolve to a known DTC code",
            False,
            dangling_related == 0,
            f"{dangling_related} related codes not in the database (informational)",
            dangling_related,
        )
    )

    unreviewed_sources = _scalar(
        conn,
        """
        SELECT COUNT(*) FROM data_sources
        WHERE legal_review_status <> 'approved' AND redistribution_allowed = 1
        """,
    )
    checks.append(
        DatabaseCheck(
            "D007_licence_review",
            "sources marked redistributable have an approved legal review",
            public,
            unreviewed_sources == 0,
            f"{unreviewed_sources} sources need a legal review before public distribution",
            unreviewed_sources,
        )
    )

    claims_without_record = _scalar(
        conn,
        """
        SELECT COUNT(*) FROM provenance_claims
        WHERE source_record_id IS NULL AND is_derived = 0
        """,
    )
    checks.append(
        DatabaseCheck(
            "D008_claims_have_source_records",
            "non-derived claims point at an immutable source record",
            True,
            claims_without_record == 0,
            f"{claims_without_record} claims without source_record_id",
            claims_without_record,
        )
    )

    empty_definitions = _scalar(
        conn,
        """
        SELECT COUNT(*) FROM dtc_definitions
        WHERE (title IS NULL OR TRIM(title) = '') AND (description IS NULL OR TRIM(description) = '')
        """,
    )
    checks.append(
        DatabaseCheck(
            "D009_definitions_not_empty",
            "no empty definition rows",
            True,
            empty_definitions == 0,
            f"{empty_definitions} empty definitions",
            empty_definitions,
        )
    )

    negative_estimates = _scalar(
        conn,
        """
        SELECT COUNT(*) FROM dtc_repairs
        WHERE cost_min < 0 OR cost_max < 0 OR hours_min < 0 OR hours_max < 0
        """,
    )
    checks.append(
        DatabaseCheck(
            "D010_numeric_sanity",
            "no negative cost/hour estimates",
            True,
            negative_estimates == 0,
            f"{negative_estimates} negative estimates",
            negative_estimates,
        )
    )

    # Every fact reaches a table through provenance_claims -> data_sources, so the
    # source registry is the single place where a licence leak can be detected.
    unlicensed_sources = _scalar(
        conn,
        """
        SELECT COUNT(*) FROM data_sources
        WHERE legal_review_status <> 'approved' OR COALESCE(redistribution_allowed, 0) = 0
        """,
    )
    rows_from_unlicensed = _scalar(
        conn,
        """
        SELECT COUNT(*) FROM provenance_claims p
        JOIN data_sources s ON s.id = p.source_id
        WHERE s.legal_review_status <> 'approved' OR COALESCE(s.redistribution_allowed, 0) = 0
        """,
    )
    stray_evidence = _scalar(
        conn,
        """
        SELECT COUNT(*) FROM conflict_evidence e
        WHERE e.source_slug NOT IN (SELECT slug FROM data_sources)
        """,
    )
    leak = unlicensed_sources + rows_from_unlicensed + stray_evidence
    checks.append(
        DatabaseCheck(
            "D011_public_source_set",
            "a public build contains no data from a non-redistributable source",
            public,
            leak == 0,
            (
                f"{unlicensed_sources} unlicensed source(s), "
                f"{rows_from_unlicensed} fact(s) and {stray_evidence} conflict evidence row(s) "
                "outside the licensed set"
            ),
            leak,
        )
    )

    return checks


def failed_blocking(checks: list[DatabaseCheck]) -> list[DatabaseCheck]:
    return [c for c in checks if c.blocking and not c.passed]
