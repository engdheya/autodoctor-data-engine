"""Measured coverage of a built database - what it actually contains.

The phase-1 data report answers "how many rows did we load". This module answers
the only question a product owner cares about: **of the population we claim to
support, how much carries each piece of information?**

Every ratio in here therefore prints its denominator explicitly. A percentage
over a denominator nobody declared is how coverage reports lie, so each block
carries the population it was computed over and the ones it deliberately
excludes.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: the population the product claims to support, and the one it does not.
SCOPE = {
    "declared": [
        "DTC identities present in the licence-cleared sources (generic OBD-II / SAE J2012 "
        "and manufacturer-specific codes from Wal33D)",
        "English titles and descriptions",
        "causes, symptoms, repairs, related codes and risk flags where the source provides them",
        "compact provenance for every fact (source, commit, licence, verification status)",
    ],
    "not_declared": [
        "Arabic definitions (no reviewed translation exists yet - see ARABIC coverage)",
        "diagnostic inspection procedures (no licensed source; table exists, content does not)",
        "vehicle / model / engine / ECU applicability (no licence-cleared vehicle dataset)",
        "UDS DIDs and proprietary PIDs (not imported)",
        "country- or market-specific statements (no source documents them)",
    ],
}


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _scalar(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
        ).fetchone()
        is not None
    )


def _ratio(part: int, whole: int) -> dict[str, int | float | None]:
    return {
        "count": part,
        "denominator": whole,
        "percent": round(100.0 * part / whole, 1) if whole else None,
    }


def coverage_report(conn: sqlite3.Connection) -> dict[str, Any]:
    """Every number is queried; nothing is estimated."""
    report: dict[str, Any] = {
        "generated_at": _now(),
        "scope": SCOPE,
        "dtc": {},
        "content": {},
        "vehicles": {},
        "pids": {},
        "procedures": {},
        "language": {},
        "conflicts": {},
        "provenance": {},
    }

    # ---- DTC population ---------------------------------------------------
    dtc = report["dtc"]
    total = _scalar(conn, "SELECT COUNT(*) FROM dtc_codes")
    dtc["identities"] = total
    dtc["distinct_codes"] = _scalar(conn, "SELECT COUNT(DISTINCT code) FROM dtc_codes")

    by_context = {
        str(row[0]): int(row[1])
        for row in conn.execute(
            "SELECT context_type, COUNT(*) FROM dtc_codes GROUP BY context_type ORDER BY 1"
        )
    }
    dtc["by_context"] = by_context
    by_category = {
        str(row[0] or "unknown"): int(row[1])
        for row in conn.execute(
            "SELECT category, COUNT(*) FROM dtc_codes GROUP BY 1 ORDER BY 1"
        )
    }
    dtc["by_category"] = by_category
    by_family = {
        str(row[0]): int(row[1])
        for row in conn.execute(
            "SELECT UPPER(SUBSTR(code, 1, 1)) AS family, COUNT(*) FROM dtc_codes "
            "GROUP BY 1 ORDER BY 1"
        )
    }
    dtc["by_family"] = by_family
    dtc["by_standard"] = {
        str(row[0]): int(row[1])
        for row in conn.execute(
            "SELECT standard, COUNT(*) FROM dtc_codes GROUP BY 1 ORDER BY 2 DESC"
        )
    }
    dtc["manufacturer_contexts"] = _scalar(
        conn, "SELECT COUNT(*) FROM dtc_codes WHERE context_type = 'manufacturer'"
    )
    dtc["manufacturers_with_codes"] = _scalar(
        conn, "SELECT COUNT(DISTINCT manufacturer_id) FROM dtc_codes "
        "WHERE manufacturer_id IS NOT NULL"
    )
    dtc["ecu_contexts"] = _scalar(
        conn, "SELECT COUNT(*) FROM dtc_codes WHERE context_type = 'ecu'"
    )
    dtc["vehicle_contexts"] = _scalar(
        conn, "SELECT COUNT(*) FROM dtc_codes WHERE context_type = 'vehicle_variant'"
    )

    # ---- per-code content coverage (the honest part) ----------------------
    # The denominator is every identity we ship, not "the rows that happen to
    # have an answer".
    content = report["content"]
    content["identities"] = total
    content["with_definition_any_language"] = _scalar(
        conn,
        "SELECT COUNT(DISTINCT dtc_code_id) FROM dtc_definitions",
    )
    content["with_english_definition"] = _scalar(
        conn, "SELECT COUNT(DISTINCT dtc_code_id) FROM dtc_definitions WHERE language = 'en'"
    )
    content["with_description"] = _scalar(
        conn,
        "SELECT COUNT(DISTINCT dtc_code_id) FROM dtc_definitions "
        "WHERE description IS NOT NULL AND TRIM(description) <> ''",
    )
    content["with_causes"] = _scalar(
        conn, "SELECT COUNT(DISTINCT dtc_code_id) FROM dtc_causes"
    )
    content["with_symptoms"] = _scalar(
        conn, "SELECT COUNT(DISTINCT dtc_code_id) FROM dtc_symptoms"
    )
    content["with_tests"] = _scalar(conn, "SELECT COUNT(DISTINCT dtc_code_id) FROM dtc_tests")
    content["with_repairs"] = _scalar(
        conn, "SELECT COUNT(DISTINCT dtc_code_id) FROM dtc_repairs"
    )
    content["with_related_codes"] = _scalar(
        conn, "SELECT COUNT(DISTINCT dtc_code_id) FROM dtc_related_codes"
    )
    content["with_components"] = _scalar(
        conn, "SELECT COUNT(DISTINCT dtc_code_id) FROM dtc_components"
    )
    content["with_risk_level"] = _scalar(
        conn, "SELECT COUNT(*) FROM dtc_flags WHERE risk_level IS NOT NULL"
    )
    content["with_mil_flag"] = _scalar(
        conn, "SELECT COUNT(*) FROM dtc_flags WHERE mil IS NOT NULL"
    )
    content["risky_or_worse"] = _scalar(
        conn, "SELECT COUNT(*) FROM dtc_flags WHERE risk_level IN ('high', 'critical')"
    )
    # the diagnostic denominator: identities that carry causes (what a mechanic
    # will actually read), reported so nobody mistakes title-only coverage for
    # diagnosis-ready data
    content["diagnosis_ready"] = content["with_causes"]
    rows = []
    for key in (
        "with_english_definition",
        "with_description",
        "with_causes",
        "with_symptoms",
        "with_tests",
        "with_repairs",
        "with_related_codes",
        "with_risk_level",
    ):
        rows.append({"field": key, **_ratio(content[key], total)})
    content["coverage"] = rows

    # ---- vehicles ---------------------------------------------------------
    vehicles = report["vehicles"]
    vehicles["manufacturers"] = _scalar(conn, "SELECT COUNT(*) FROM manufacturers")
    vehicles["vehicles"] = _scalar(conn, "SELECT COUNT(*) FROM vehicles")
    vehicles["variants"] = _scalar(conn, "SELECT COUNT(*) FROM vehicle_variants")
    vehicles["ecus"] = _scalar(conn, "SELECT COUNT(*) FROM ecus")
    vehicles["ecu_links"] = _scalar(conn, "SELECT COUNT(*) FROM vehicle_ecu_links")
    vehicles["dtc_ecu_links"] = _scalar(
        conn, "SELECT COUNT(*) FROM dtc_codes WHERE ecu_id IS NOT NULL"
    )
    vehicles["dtc_vehicle_links"] = _scalar(
        conn, "SELECT COUNT(*) FROM dtc_codes WHERE vehicle_variant_id IS NOT NULL"
    )

    # ---- PIDs -------------------------------------------------------------
    pids = report["pids"]
    pids["rows"] = _scalar(conn, "SELECT COUNT(*) FROM pids")
    pids["with_name_en"] = _scalar(
        conn, "SELECT COUNT(*) FROM pids p WHERE EXISTS "
        "(SELECT 1 FROM pid_texts t WHERE t.pid_id = p.id AND t.language = 'en')"
    )
    pids["with_name_ar"] = _scalar(
        conn, "SELECT COUNT(*) FROM pids p WHERE EXISTS "
        "(SELECT 1 FROM pid_texts t WHERE t.pid_id = p.id AND t.language = 'ar')"
    )
    pids["with_formula"] = _scalar(
        conn, "SELECT COUNT(*) FROM pids WHERE formula IS NOT NULL AND TRIM(formula) <> ''"
    )
    pids["with_range"] = _scalar(
        conn, "SELECT COUNT(*) FROM pids WHERE range_min IS NOT NULL AND range_max IS NOT NULL"
    )
    pids["with_unit"] = _scalar(
        conn, "SELECT COUNT(*) FROM pids WHERE unit IS NOT NULL AND TRIM(unit) <> ''"
    )
    pids["by_scope"] = {
        str(row[0] or "unknown"): int(row[1])
        for row in conn.execute("SELECT scope, COUNT(*) FROM pids GROUP BY 1 ORDER BY 1")
    }
    pids["by_mode"] = {
        str(row[0] or "unknown"): int(row[1])
        for row in conn.execute("SELECT mode, COUNT(*) FROM pids GROUP BY 1 ORDER BY 1")
    }

    # ---- procedures -------------------------------------------------------
    procedures = report["procedures"]
    procedures["procedures"] = _scalar(conn, "SELECT COUNT(*) FROM dtc_tests")
    procedures["with_text"] = _scalar(conn, "SELECT COUNT(DISTINCT test_id) FROM dtc_test_texts")
    procedures["codes_with_procedure"] = _scalar(
        conn, "SELECT COUNT(DISTINCT dtc_code_id) FROM dtc_tests"
    )
    procedures["steps_table"] = _table_exists(conn, "dtc_test_steps")
    procedures["steps"] = (
        _scalar(conn, "SELECT COUNT(*) FROM dtc_test_steps")
        if procedures["steps_table"]
        else 0
    )
    procedures["has_content"] = procedures["procedures"] > 0

    # ---- language ---------------------------------------------------------
    language = report["language"]
    language["definitions_en"] = _scalar(
        conn, "SELECT COUNT(*) FROM dtc_definitions WHERE language = 'en'"
    )
    language["definitions_ar"] = _scalar(
        conn, "SELECT COUNT(*) FROM dtc_definitions WHERE language = 'ar'"
    )
    language["definitions_other"] = _scalar(
        conn,
        "SELECT COUNT(*) FROM dtc_definitions WHERE language NOT IN ('en', 'ar')",
    )
    language["identities_with_arabic"] = _scalar(
        conn, "SELECT COUNT(DISTINCT dtc_code_id) FROM dtc_definitions WHERE language = 'ar'"
    )
    language["arabic_reviewed"] = _scalar(
        conn,
        "SELECT COUNT(*) FROM dtc_definitions WHERE language = 'ar' AND translation_reviewed = 1",
    )
    language["translations_rows"] = _scalar(conn, "SELECT COUNT(*) FROM translations")
    language["arabic_coverage"] = _ratio(language["identities_with_arabic"], total)

    # ---- conflicts --------------------------------------------------------
    conflicts = report["conflicts"]
    conflicts["total"] = _scalar(conn, "SELECT COUNT(*) FROM conflicts")
    conflicts["open"] = _scalar(
        conn, "SELECT COUNT(*) FROM conflicts WHERE status = 'needs_review'"
    )
    conflicts["by_status"] = {
        str(row[0]): int(row[1])
        for row in conn.execute("SELECT status, COUNT(*) FROM conflicts GROUP BY 1 ORDER BY 1")
    }
    conflicts["by_type"] = {
        str(row[0]): int(row[1])
        for row in conn.execute(
            "SELECT conflict_type, COUNT(*) FROM conflicts GROUP BY 1 ORDER BY 1"
        )
    }
    conflicts["codes_affected"] = _scalar(
        conn, "SELECT COUNT(DISTINCT dtc_code_id) FROM conflicts"
    )
    conflicts["definitions_conflicting"] = _scalar(
        conn, "SELECT COUNT(*) FROM dtc_definitions WHERE verification_status = 'conflicting'"
    )

    # ---- provenance -------------------------------------------------------
    provenance = report["provenance"]
    provenance["claims"] = _scalar(conn, "SELECT COUNT(*) FROM provenance_claims")
    provenance["evidence"] = _scalar(conn, "SELECT COUNT(*) FROM dtc_evidence_sources")
    provenance["sources"] = _scalar(conn, "SELECT COUNT(*) FROM data_sources")
    # the engineering database has the full claim matrix (the app bundle only has
    # the compact provenance_summary, so this query must work on claims)
    provenance["definitions_multi_source"] = _scalar(
        conn,
        "SELECT COUNT(*) FROM (SELECT entity_id FROM provenance_claims "
        "WHERE entity_type = 'dtc_definition' GROUP BY entity_id "
        "HAVING COUNT(DISTINCT source_id) > 1)",
    )
    provenance["identities_multi_source"] = _scalar(
        conn,
        "SELECT COUNT(*) FROM (SELECT p.entity_id FROM provenance_claims p "
        "WHERE p.entity_type = 'dtc_code' GROUP BY p.entity_id "
        "HAVING COUNT(DISTINCT p.source_id) > 1)",
    )
    provenance["per_source"] = {
        str(row[0]): int(row[1])
        for row in conn.execute(
            "SELECT s.slug, COUNT(*) FROM provenance_claims p "
            "JOIN data_sources s ON s.id = p.source_id GROUP BY 1 ORDER BY 2 DESC"
        )
    }
    provenance["verification_status"] = {
        str(row[0]): int(row[1])
        for row in conn.execute(
            "SELECT verification_status, COUNT(*) FROM dtc_definitions GROUP BY 1 ORDER BY 2 DESC"
        )
    }

    report["declared_support"] = _declared_support(report)
    return report


def _declared_support(report: dict[str, Any]) -> dict[str, Any]:
    """A machine-checkable summary of what may be claimed publicly."""
    dtc = report["dtc"]
    content = report["content"]
    return {
        "dtc_identities": dtc["identities"],
        "dtc_distinct_codes": dtc["distinct_codes"],
        "diagnosis_ready_identities": content["diagnosis_ready"],
        "arabic_identities": report["language"]["identities_with_arabic"],
        "procedures": report["procedures"]["procedures"],
        "vehicle_links": report["vehicles"]["dtc_vehicle_links"],
        "ecu_links": report["vehicles"]["dtc_ecu_links"],
        "claim": (
            "definition and diagnostic content (causes/symptoms/repairs/flags) for the "
            "declared DTC population, English only"
        ),
        "not_supported": [item for item in SCOPE["not_declared"]],
    }


def _bar(percent: float | None, width: int = 20) -> str:
    if percent is None:
        return "-"
    filled = int(round(percent / 100 * width))
    return "#" * filled + "." * (width - filled)


def render_coverage_markdown(report: dict[str, Any]) -> str:
    dtc = report["dtc"]
    content = report["content"]
    vehicles = report["vehicles"]
    pids = report["pids"]
    procedures = report["procedures"]
    language = report["language"]
    conflicts = report["conflicts"]
    provenance = report["provenance"]

    lines: list[str] = []
    add = lines.append
    add("# Data coverage report")
    add("")
    add(f"Generated: {report['generated_at']}")
    add("")
    add("Every number is a query against the built database. Ratios print their denominator: the")
    add("population we declare support for is stated first, so a percentage can never be read")
    add("against a denominator that was quietly narrowed.")
    add("")
    add("## Declared scope")
    add("")
    add("**Supported:**")
    for item in report["scope"]["declared"]:
        add(f"* {item}")
    add("")
    add("**Explicitly not supported (and why):**")
    for item in report["scope"]["not_declared"]:
        add(f"* {item}")
    add("")
    add("## DTC population")
    add("")
    add("| Dimension | Count |")
    add("| --- | ---: |")
    add(f"| DTC identities (code + context) | {dtc['identities']:,} |")
    add(f"| Distinct codes | {dtc['distinct_codes']:,} |")
    for key, value in dtc["by_context"].items():
        add(f"| — context `{key}` | {value:,} |")
    for key, value in dtc["by_family"].items():
        add(f"| — family {key} | {value:,} |")
    add(f"| Manufacturer contexts | {dtc['manufacturer_contexts']:,} |")
    add(f"| Manufacturers with codes | {dtc['manufacturers_with_codes']:,} |")
    add(f"| ECU contexts | {dtc['ecu_contexts']:,} |")
    add(f"| Vehicle-variant contexts | {dtc['vehicle_contexts']:,} |")
    add("")
    add("## Content coverage per identity")
    add("")
    add(f"Denominator: **{content['identities']:,} identities** the database ships.")
    add("")
    add("| Field | Identities | Denominator | Coverage | |")
    add("| --- | ---: | ---: | ---: | --- |")
    for row in content["coverage"]:
        pct = "-" if row["percent"] is None else f"{row['percent']}%"
        add(f"| {row['field']} | {row['count']:,} | {row['denominator']:,} | {pct} | `{_bar(row['percent'])}` |")
    add("")
    add(f"**Diagnosis-ready identities** (have at least one cause): **{content['diagnosis_ready']:,}** "
        f"of {content['identities']:,}.")
    add("")
    add("A definition without causes, symptoms or repairs is a *label*, not a diagnosis. Those rows")
    add("are counts in this table, never presented in the app as diagnostic advice.")
    add("")
    add("## Vehicle coverage")
    add("")
    add("| Table | Rows |")
    add("| --- | ---: |")
    add(f"| manufacturers | {vehicles['manufacturers']:,} |")
    add(f"| vehicles | {vehicles['vehicles']:,} |")
    add(f"| vehicle variants | {vehicles['variants']:,} |")
    add(f"| ECUs | {vehicles['ecus']:,} |")
    add(f"| vehicle ↔ ECU links | {vehicles['ecu_links']:,} |")
    add(f"| DTCs with an ECU context | {vehicles['dtc_ecu_links']:,} |")
    add(f"| DTCs with a vehicle context | {vehicles['dtc_vehicle_links']:,} |")
    add("")
    if not vehicles["vehicles"] and not vehicles["ecus"]:
        add("> No vehicle or ECU rows exist in this edition: no licence-cleared source provides")
        add("> them. Vehicle-based search is therefore **not supported** and must not be shown as")
        add("> a feature. See the accepted scope above.")
        add("")
    add("## PID coverage")
    add("")
    add("| Metric | Count | Denominator | Coverage |")
    add("| --- | ---: | ---: | ---: |")
    for key, label in (
        ("with_name_en", "PIDs with an English name"),
        ("with_name_ar", "PIDs with an Arabic name"),
        ("with_formula", "PIDs with a scaling formula"),
        ("with_range", "PIDs with min and max"),
        ("with_unit", "PIDs with a unit"),
    ):
        pct = _ratio(pids[key], pids["rows"])["percent"]
        add(f"| {label} | {pids[key]:,} | {pids['rows']:,} | {'-' if pct is None else f'{pct}%'} |")
    add("")
    if pids["by_scope"]:
        add("By scope: " + ", ".join(f"`{k}` {v:,}" for k, v in pids["by_scope"].items()))
        add("")
    add("## Diagnostic procedures")
    add("")
    add(f"* procedures: **{procedures['procedures']:,}**")
    add(f"* procedures with text: {procedures['with_text']:,}")
    add(f"* codes with a procedure: {procedures['codes_with_procedure']:,}")
    add(f"* ordered steps: {procedures['steps']:,}")
    add("")
    if not procedures["has_content"]:
        add("> **Zero procedures.** No licence-cleared source ships inspection procedures and this")
        add("> project does not author them from memory. The schema, loader, gates and UI contract")
        add("> exist; the content does not. The app must not claim procedure coverage.")
        add("")
    add("## Language coverage")
    add("")
    add("| Metric | Count | Denominator | Coverage |")
    add("| --- | ---: | ---: | ---: |")
    add(f"| English definitions | {language['definitions_en']:,} | — | — |")
    rows = [
        ("Arabic definitions", language["definitions_ar"]),
        ("Identities with Arabic", language["identities_with_arabic"]),
    ]
    for label, value in rows:
        pct = _ratio(value, language["definitions_en"])["percent"]
        add(f"| {label} | {value:,} | {language['definitions_en']:,} English definitions | "
            f"{'-' if pct is None else f'{pct}%'} |")
    add(f"| Reviewed Arabic translations | {language['arabic_reviewed']:,} | "
        f"{language['definitions_ar']:,} Arabic definitions | "
        f"{'-' if not language['definitions_ar'] else '0%'} |")
    add(f"| Other languages (source-provided) | {language['definitions_other']:,} | — | — |")
    add("")
    add(f"Arabic coverage of the identity population: "
        f"**{language['arabic_coverage']['count']:,} / {language['arabic_coverage']['denominator']:,}**"
        if language["arabic_coverage"]["denominator"] else "Arabic coverage: no identities")
    add("")
    add("## Conflicts")
    add("")
    add("| Metric | Count |")
    add("| --- | ---: |")
    add(f"| conflicts | {conflicts['total']:,} |")
    add(f"| open (`needs_review`) | {conflicts['open']:,} |")
    add(f"| codes affected | {conflicts['codes_affected']:,} |")
    add(f"| definitions flagged `conflicting` | {conflicts['definitions_conflicting']:,} |")
    for key, value in conflicts["by_type"].items():
        add(f"| type `{key}` | {value:,} |")
    add("")
    add("## Provenance")
    add("")
    add("| Metric | Count |")
    add("| --- | ---: |")
    add(f"| sources | {provenance['sources']:,} |")
    add(f"| claims | {provenance['claims']:,} |")
    add(f"| evidence citations | {provenance['evidence']:,} |")
    add(f"| definitions from 2+ sources | {provenance['definitions_multi_source']:,} |")
    add(f"| identities from 2+ sources | {provenance['identities_multi_source']:,} |")
    add("")
    if provenance["per_source"]:
        add("Claims per source: " + ", ".join(f"`{k}` {v:,}" for k, v in provenance["per_source"].items()))
        add("")
    add("## What may be claimed publicly")
    add("")
    support = report["declared_support"]
    add(f"* {support['dtc_identities']:,} DTC identities / {support['dtc_distinct_codes']:,} distinct codes")
    add(f"* {support['diagnosis_ready_identities']:,} of them carry causes")
    add(f"* {support['arabic_identities']:,} carry Arabic, {support['procedures']:,} carry a procedure, "
        f"{support['vehicle_links']:,} carry a vehicle link")
    add("* the rest must be described in the app as *definition only*")
    add("")
    return "\n".join(lines)


def write_coverage(conn: sqlite3.Connection, reports_dir: Path) -> tuple[Path, Path]:
    import json

    reports_dir.mkdir(parents=True, exist_ok=True)
    report = coverage_report(conn)
    json_path = reports_dir / "coverage.json"
    md_path = reports_dir / "coverage.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_coverage_markdown(report) + "\n", encoding="utf-8")
    return json_path, md_path


__all__ = ["SCOPE", "coverage_report", "render_coverage_markdown", "write_coverage"]
