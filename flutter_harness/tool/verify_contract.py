#!/usr/bin/env python3
"""Run the client query contract against a built bundle.

This is the same set of statements the Flutter harness executes, run here so the
result can be recorded in CI and in the release notes. It does not replace the
on-device run: it proves the SQL and the data, not the Android runtime.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

SCENARIOS = {
    "1_generic_lookup": (
        "SELECT code, title_en, content_tier, cause_count, symptom_count, repair_count, "
        "risk_level FROM v_dtc_search WHERE code = ? AND context_type = 'generic'",
        ("P0301",),
    ),
    "2_manufacturer_context": (
        "SELECT code, context_type, manufacturer, title_en, content_tier FROM v_dtc_search "
        "WHERE code = ? ORDER BY context_type, manufacturer",
        ("P1690",),
    ),
    "3_vehicle_search": (
        "SELECT COUNT(*) AS n FROM v_vehicles WHERE manufacturer LIKE ?",
        ("%",),
    ),
    "4_code_without_diagnostics": (
        "SELECT code, title_en, content_tier, cause_count FROM v_dtc_search "
        "WHERE content_tier = 'definition_only' ORDER BY code LIMIT 3",
        (),
    ),
    "5_arabic": (
        "SELECT COUNT(*) AS n FROM v_dtc_search WHERE title_ar IS NOT NULL",
        (),
    ),
    "6_provenance": (
        "SELECT source_slug, data_license, commit_sha, verification_status FROM v_dtc_provenance "
        "WHERE entity_type = 'dtc_code' AND entity_id = "
        "(SELECT dtc_code_id FROM v_dtc_search WHERE code = 'P0301' AND context_type = 'generic')",
        (),
    ),
    "7_procedures": (
        "SELECT COUNT(*) AS n FROM v_dtc_tests",
        (),
    ),
    "8_conflicts": (
        "SELECT COUNT(*) AS n, SUM(status = 'needs_review') AS open FROM v_dtc_conflicts",
        (),
    ),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    conn = sqlite3.connect(f"file:{args.database}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    results: dict[str, object] = {}

    checks = {
        "integrity_check": conn.execute("PRAGMA integrity_check").fetchone()[0],
        "foreign_key_check": len(conn.execute("PRAGMA foreign_key_check").fetchall()),
        "views": [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'view' ORDER BY name"
            )
        ],
    }

    for name, (sql, params) in SCENARIOS.items():
        start = time.perf_counter()
        rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
        results[name] = {
            "rows": rows,
            "ms": round((time.perf_counter() - start) * 1000, 2),
        }

    payload = {
        "database": str(args.database),
        "checks": checks,
        "scenarios": results,
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"written {args.out}")
    else:
        print(text)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
