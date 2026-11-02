"""Per-code completeness: what every identity actually carries, and what is missing.

Coverage percentages answer "how much of the population has a cause". This module
answers the question a reviewer asks next: *which* codes are incomplete, and in
what way - so the gap can be worked on code by code instead of being summarised.

Nothing here fills a field. A missing value is reported as missing.
"""

from __future__ import annotations

import csv
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: the facts a diagnostic card is built from, in display order
FIELDS = (
    "definition_en",
    "description_en",
    "causes",
    "symptoms",
    "repairs",
    "tests",
    "related_codes",
    "risk_level",
    "mil",
    "emissions_relevant",
)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def completeness_report(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT
            c.id,
            c.code,
            c.context_type,
            c.context_key,
            m.name AS manufacturer,
            EXISTS (SELECT 1 FROM dtc_definitions d
                     WHERE d.dtc_code_id = c.id AND d.language = 'en')            AS definition_en,
            EXISTS (SELECT 1 FROM dtc_definitions d
                     WHERE d.dtc_code_id = c.id AND d.language = 'en'
                       AND d.description IS NOT NULL AND TRIM(d.description) <> '') AS description_en,
            EXISTS (SELECT 1 FROM dtc_causes x WHERE x.dtc_code_id = c.id)       AS causes,
            EXISTS (SELECT 1 FROM dtc_symptoms x WHERE x.dtc_code_id = c.id)     AS symptoms,
            EXISTS (SELECT 1 FROM dtc_repairs x WHERE x.dtc_code_id = c.id)      AS repairs,
            EXISTS (SELECT 1 FROM dtc_tests x WHERE x.dtc_code_id = c.id)        AS tests,
            EXISTS (SELECT 1 FROM dtc_related_codes x WHERE x.dtc_code_id = c.id) AS related_codes,
            EXISTS (SELECT 1 FROM dtc_flags x
                     WHERE x.dtc_code_id = c.id AND x.risk_level IS NOT NULL)     AS risk_level,
            EXISTS (SELECT 1 FROM dtc_flags x
                     WHERE x.dtc_code_id = c.id AND x.mil IS NOT NULL)            AS mil,
            EXISTS (SELECT 1 FROM dtc_flags x
                     WHERE x.dtc_code_id = c.id AND x.emissions_relevant IS NOT NULL)
                                                                                  AS emissions_relevant
        FROM dtc_codes c
        LEFT JOIN manufacturers m ON m.id = c.manufacturer_id
        ORDER BY c.context_type, c.code
        """
    ).fetchall()

    items: list[dict[str, Any]] = []
    for row in rows:
        present = [name for name in FIELDS if row[name]]
        missing = [name for name in FIELDS if not row[name]]
        items.append(
            {
                "dtc_code_id": int(row["id"]),
                "code": str(row["code"]),
                "context_type": str(row["context_type"]),
                "context_key": str(row["context_key"]),
                "manufacturer": row["manufacturer"],
                "present": present,
                "missing": missing,
                "field_count": len(present),
                "tier": "diagnosis_ready" if row["causes"] else "definition_only",
            }
        )

    total = len(items)
    by_field = {
        name: sum(1 for item in items if name in item["present"]) for name in FIELDS
    }
    by_tier = {
        "diagnosis_ready": sum(1 for item in items if item["tier"] == "diagnosis_ready"),
        "definition_only": sum(1 for item in items if item["tier"] == "definition_only"),
    }
    by_context: dict[str, dict[str, int]] = {}
    for item in items:
        bucket = by_context.setdefault(
            item["context_type"], {"identities": 0, "definition_only": 0}
        )
        bucket["identities"] += 1
        if item["tier"] == "definition_only":
            bucket["definition_only"] += 1

    # the concrete work lists, not just the totals
    missing_causes = [i["code"] for i in items if "causes" in i["missing"]]
    missing_symptoms = [
        i["code"] for i in items if "causes" in i["present"] and "symptoms" in i["missing"]
    ]
    for item in items:
        item["record_status"] = "complete" if not item["missing"] else "incomplete"

    return {
        "generated_at": _now(),
        "fields": list(FIELDS),
        "totals": {
            "identities": total,
            "complete": sum(1 for i in items if not i["missing"]),
            "with_causes": by_tier["diagnosis_ready"],
            "definition_only": by_tier["definition_only"],
        },
        "by_field": by_field,
        "by_context": by_context,
        "worklists": {
            "missing_causes": missing_causes,
            "missing_symptoms_where_causes_exist": missing_symptoms,
        },
        "items": items,
    }


def render_completeness(report: dict[str, Any], *, sample: int = 15) -> str:
    totals = report["totals"]
    lines: list[str] = []
    add = lines.append
    add("# Per-code completeness")
    add("")
    add(f"Generated: {report['generated_at']}")
    add("")
    add("Every identity the database ships, with the diagnostic facts it carries and the ones it")
    add("does not. A missing fact is reported as missing: nothing is filled in.")
    add("")
    add("| Metric | Count | Denominator |")
    add("| --- | ---: | ---: |")
    total = totals["identities"]
    add(f"| identities | {total:,} | — |")
    add(f"| diagnosis-ready (has causes) | {totals['with_causes']:,} | {total:,} |")
    add(f"| definition only | {totals['definition_only']:,} | {total:,} |")
    add(f"| complete on every tracked field | {totals['complete']:,} | {total:,} |")
    add("")
    add("## Field coverage")
    add("")
    add("| Field | Identities | Missing |")
    add("| --- | ---: | ---: |")
    for name, count in report["by_field"].items():
        add(f"| {name} | {count:,} | {total - count:,} |")
    add("")
    add("## By context")
    add("")
    add("| Context | Identities | definition only |")
    add("| --- | ---: | ---: |")
    for name, bucket in sorted(report["by_context"].items(), key=lambda kv: -kv[1]["identities"]):
        add(f"| {name} | {bucket['identities']:,} | {bucket['definition_only']:,} |")
    add("")
    missing_causes = report["worklists"]["missing_causes"]
    add(f"## Work list: codes with no causes ({len(missing_causes):,})")
    add("")
    if missing_causes:
        add("Text: " + ", ".join(missing_causes[:sample]) + (" …" if len(missing_causes) > sample else ""))
    else:
        add("none")
    add("")
    missing_symptoms = report["worklists"]["missing_symptoms_where_causes_exist"]
    add(f"## Work list: codes with causes but no symptoms ({len(missing_symptoms):,})")
    add("")
    if missing_symptoms:
        add("Text: " + ", ".join(missing_symptoms[:sample])
            + (" …" if len(missing_symptoms) > sample else ""))
    else:
        add("none")
    add("")
    return "\n".join(lines)


def write_completeness(
    conn: sqlite3.Connection, reports_dir: Path
) -> tuple[Path, Path, Path]:
    import json

    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    report = completeness_report(conn)

    json_path = reports_dir / "completeness.json"
    md_path = reports_dir / "completeness.md"
    csv_path = reports_dir / "completeness.csv"

    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    md_path.write_text(render_completeness(report) + "\n", encoding="utf-8")

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["code", "context_type", "context_key", "manufacturer", "tier",
                         "field_count", *report["fields"]])
        for item in report["items"]:
            writer.writerow([
                item["code"],
                item["context_type"],
                item["context_key"],
                item["manufacturer"] or "",
                item["tier"],
                item["field_count"],
                *(1 if field in item["present"] else 0 for field in report["fields"]),
            ])
    return json_path, md_path, csv_path


__all__ = ["FIELDS", "completeness_report", "render_completeness", "write_completeness"]
