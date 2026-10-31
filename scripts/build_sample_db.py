#!/usr/bin/env python3
"""Build a small, real sample database for trying queries by hand.

It takes a *published* release bundle and keeps a few hundred generic codes with
everything attached to them (definitions, causes, symptoms, repairs, components,
related codes, flags, evidence links, conflicts and the compact provenance), so
that `sqlite3 data/samples/autodoctor-sample.sqlite` is useful without shipping a
52 MB file in git.

    python scripts/build_sample_db.py \
        --source data/exports/autodoctor-app-0.4.0-public.sqlite \
        --out data/samples/autodoctor-sample.sqlite \
        --limit 250

The sample is generated, never hand-edited, and `data/samples/README.md` explains
what it contains and what it deliberately does not.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from autodoctor_data_engine.database.app_export import (  # noqa: E402
    LicenceError,
    _verify_views,
)

DEFAULT_CODES = [
    # the documented walkthrough plus codes almost every scan produces
    "P0301", "P0300", "P0302", "P0171", "P0172", "P0420", "P0442", "P0455",
    "P0128", "P0113", "P0102", "P0133", "P0135", "P0141", "P0401", "P0402",
    "P0700", "P0741", "P0500", "P0562", "U0100", "B0001", "C0035",
]

#: table -> SQL body that selects the rows to keep from the source database
CONTENT_SQL = {
    "data_sources": "SELECT * FROM src.data_sources",
    "data_versions": "SELECT * FROM src.data_versions",
    "db_versions": "SELECT * FROM src.db_versions",
    "manufacturers": "SELECT * FROM src.manufacturers",
    "pids": "SELECT * FROM src.pids",
    "pid_texts": "SELECT * FROM src.pid_texts",
    "dtc_codes": "SELECT * FROM src.dtc_codes WHERE id IN (SELECT id FROM codes)",
    "dtc_definitions": "SELECT * FROM src.dtc_definitions WHERE dtc_code_id IN (SELECT id FROM codes)",
    "dtc_causes": "SELECT * FROM src.dtc_causes WHERE dtc_code_id IN (SELECT id FROM codes)",
    "dtc_cause_texts": (
        "SELECT t.* FROM src.dtc_cause_texts t WHERE t.cause_id IN "
        "(SELECT id FROM src.dtc_causes WHERE dtc_code_id IN (SELECT id FROM codes))"
    ),
    "dtc_symptoms": "SELECT * FROM src.dtc_symptoms WHERE dtc_code_id IN (SELECT id FROM codes)",
    "dtc_symptom_texts": (
        "SELECT t.* FROM src.dtc_symptom_texts t WHERE t.symptom_id IN "
        "(SELECT id FROM src.dtc_symptoms WHERE dtc_code_id IN (SELECT id FROM codes))"
    ),
    "dtc_tests": "SELECT * FROM src.dtc_tests WHERE dtc_code_id IN (SELECT id FROM codes)",
    "dtc_test_texts": (
        "SELECT t.* FROM src.dtc_test_texts t WHERE t.test_id IN "
        "(SELECT id FROM src.dtc_tests WHERE dtc_code_id IN (SELECT id FROM codes))"
    ),
    "dtc_repairs": "SELECT * FROM src.dtc_repairs WHERE dtc_code_id IN (SELECT id FROM codes)",
    "dtc_repair_texts": (
        "SELECT t.* FROM src.dtc_repair_texts t WHERE t.repair_id IN "
        "(SELECT id FROM src.dtc_repairs WHERE dtc_code_id IN (SELECT id FROM codes))"
    ),
    "dtc_components": "SELECT * FROM src.dtc_components WHERE dtc_code_id IN (SELECT id FROM codes)",
    "dtc_component_texts": (
        "SELECT t.* FROM src.dtc_component_texts t WHERE t.component_id IN "
        "(SELECT id FROM src.dtc_components WHERE dtc_code_id IN (SELECT id FROM codes))"
    ),
    "dtc_related_codes": "SELECT * FROM src.dtc_related_codes WHERE dtc_code_id IN (SELECT id FROM codes)",
    "dtc_evidence_sources": (
        "SELECT * FROM src.dtc_evidence_sources WHERE dtc_code_id IN (SELECT id FROM codes)"
    ),
    "dtc_flags": "SELECT * FROM src.dtc_flags WHERE dtc_code_id IN (SELECT id FROM codes)",
    "translations": "SELECT * FROM src.translations WHERE dtc_code_id IN (SELECT id FROM codes)",
    "conflicts": "SELECT * FROM src.conflicts WHERE dtc_code_id IN (SELECT id FROM codes)",
    "conflict_evidence": (
        "SELECT e.* FROM src.conflict_evidence e WHERE e.conflict_id IN "
        "(SELECT id FROM src.conflicts WHERE dtc_code_id IN (SELECT id FROM codes))"
    ),
    "provenance_summary": (
        "SELECT * FROM src.provenance_summary WHERE "
        "(entity_type = 'dtc_code' AND entity_id IN (SELECT id FROM codes)) OR "
        "(entity_type IN ('dtc_definition', 'dtc_cause', 'dtc_symptom', 'dtc_test', "
        "'dtc_repair', 'dtc_component', 'dtc_related_code', 'dtc_flags') AND entity_id IN "
        "(SELECT id FROM src.dtc_definitions WHERE dtc_code_id IN (SELECT id FROM codes)) "
        "OR entity_id IN (SELECT id FROM src.dtc_causes WHERE dtc_code_id IN (SELECT id FROM codes)) "
        "OR entity_id IN (SELECT id FROM src.dtc_symptoms WHERE dtc_code_id IN (SELECT id FROM codes)) "
        "OR entity_id IN (SELECT id FROM src.dtc_repairs WHERE dtc_code_id IN (SELECT id FROM codes)) "
        "OR entity_id IN (SELECT id FROM src.dtc_components WHERE dtc_code_id IN (SELECT id FROM codes))"
        ")"
    ),
}


def build_sample(
    source: Path, target: Path, *, limit: int, codes: list[str], allow_private: bool = False
) -> dict[str, int]:
    if not source.is_file():
        raise SystemExit(f"source bundle not found: {source}")
    if not allow_private:
        # check the source before anything is written, so a refused run leaves
        # no half-built artifact behind
        check = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        try:
            offenders = [
                row[0]
                for row in check.execute(
                    "SELECT slug FROM data_sources WHERE legal_review_status <> 'approved' "
                    "OR COALESCE(redistribution_allowed, 0) = 0"
                )
            ]
        finally:
            check.close()
        if offenders:
            raise LicenceError(
                "refusing to sample a non-public database: "
                + ", ".join(offenders)
                + " (use --allow-private for internal work)"
            )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)

    conn = sqlite3.connect(target, uri=True)
    try:
        # the published bundle is attached READ ONLY: it must never be modified by
        # generating a sample from it (an unqualified DROP/CREATE VIEW with the
        # source attached once cost a bundle its views)
        conn.execute(f"ATTACH DATABASE 'file:{source.resolve()}?mode=ro' AS src")
        _create_schema(conn, source)

        placeholders = ",".join("?" * len(codes))
        query = (
            "SELECT c.id, c.code FROM src.dtc_codes c "
            "WHERE c.context_type = 'generic' "
            "AND EXISTS (SELECT 1 FROM src.dtc_causes x WHERE x.dtc_code_id = c.id) "
            f"ORDER BY (c.code IN ({placeholders})) DESC, c.code LIMIT ?"
        )
        rows = conn.execute(query, (*codes, limit)).fetchall()
        conn.execute("CREATE TEMP TABLE codes (id INTEGER PRIMARY KEY)")
        conn.executemany("INSERT OR IGNORE INTO temp.codes (id) VALUES (?)", [(r[0],) for r in rows])

        counts: dict[str, int] = {}
        for table, sql in CONTENT_SQL.items():
            exists = conn.execute(
                "SELECT 1 FROM src.sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if not exists:
                continue
            try:
                cur = conn.execute(f"INSERT INTO main.{table} {sql}")
            except sqlite3.IntegrityError:
                continue
            counts[table] = int(cur.rowcount or 0)

        conn.execute(
            "UPDATE db_versions SET notes = ?, source_set = source_set",
            ("sample database generated by scripts/build_sample_db.py",),
        )
        views = [
            row[0]
            for row in conn.execute(
                "SELECT sql FROM src.sqlite_master WHERE type = 'view' AND sql IS NOT NULL"
            ).fetchall()
        ]
        conn.commit()
        conn.execute("DETACH DATABASE src")
        conn.commit()
        # views are created only after the source is detached, and always with an
        # explicit schema so they cannot land in the attached database
        for sql in views:
            conn.execute("DROP VIEW IF EXISTS main." + sql.split("VIEW", 1)[1].split()[0])
            conn.execute(_qualify_view(sql))
        conn.commit()
        conn.execute("VACUUM")
        conn.commit()
        counts["bytes"] = target.stat().st_size
        counts["codes"] = len(rows)
        conn.close()
        _verify_views(target)
        return counts
    finally:
        conn.close()


def _qualify_view(sql: str) -> str:
    """`CREATE VIEW x AS …` -> `CREATE VIEW main.x AS …`."""
    head, rest = sql.split("VIEW", 1)
    name, tail = rest.split("AS", 1)
    return f"{head}VIEW main.{name.strip()} AS{tail}"


def _create_schema(conn: sqlite3.Connection, source: Path) -> None:
    """Recreate the source's own schema (tables first, then views)."""
    statements = conn.execute(
        "SELECT sql FROM src.sqlite_master WHERE sql IS NOT NULL "
        "AND type IN (" + "'table','index'" + ") ORDER BY (type='index')"
    ).fetchall()
    for (sql,) in statements:
        if sql.startswith("CREATE TABLE") and "sqlite_" in sql:
            continue
        conn.execute(sql)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="published bundle (.sqlite)")
    parser.add_argument("--out", type=Path, default=Path("data/samples/autodoctor-sample.sqlite"))
    parser.add_argument("--limit", type=int, default=250, help="number of generic codes to keep")
    parser.add_argument("--codes", default=",".join(DEFAULT_CODES),
                        help="comma separated codes to always keep")
    parser.add_argument("--allow-private", action="store_true",
                        help="sample a database that contains sources pending licence review")
    args = parser.parse_args(argv)

    codes = [code.strip().upper() for code in args.codes.split(",") if code.strip()]
    counts = build_sample(
        args.source, args.out, limit=args.limit, codes=codes, allow_private=args.allow_private
    )
    print(f"wrote {args.out} ({counts['bytes'] / 1e6:.2f} MB)")
    for table, count in sorted(counts.items()):
        if table in {"bytes", "codes"}:
            continue
        print(f"  {table:<24}{count:>8,}")
    print(f"  codes kept              {counts['codes']:>8,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
