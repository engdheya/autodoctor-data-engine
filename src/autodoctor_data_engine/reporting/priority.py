"""Priority ranking for code review.

The client asked for review work to start with the codes that can hurt somebody, then the
codes that touch the vital systems, then the codes people actually meet in a workshop, then
the rest. Nothing here is a diagnostic judgement: the ranking only decides *the order a human
reads the codes in*, and every reason it gives is a fact stored in the database.

Two things are deliberately not invented:

* ``risk_level`` comes from the source that published it; when a source published none the
  code simply scores lower and says so.
* prevalence is a **proxy** (how many independent sources state the code and how many
  manufacturer contexts it appears in). It is not real-world usage frequency, which no source
  in the envelope provides.
"""

from __future__ import annotations

import csv
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

TIERS: dict[int, str] = {
    1: "safety - ignoring it can endanger the driver or the vehicle",
    2: "vital system - engine, brakes, steering, transmission, energy",
    3: "prevalent - stated by several sources or across many manufacturers",
    4: "remaining",
}

# Components that can take away control of the car: brakes, steering, restraint systems and
# the accelerator. Fuel delivery and injection are vital but not steering-or-stopping, so they
# sit in tier 2.
SAFETY_TERMS: tuple[str, ...] = (
    "brake",
    "abs",
    "esp",
    "stability",
    "steer",
    "airbag",
    "srs",
    "seatbelt",
    "pretensioner",
    "crash",
    "rollover",
    "throttle",
    "accelerator",
    "pedal",
)

VITAL_TERMS: tuple[str, ...] = (
    "engine",
    "fuel",
    "injector",
    "high_pressure_fuel",
    "ecm",
    "transmission",
    "gearbox",
    "coolant",
    "oil",
    "battery",
    "bms",
    "hybrid",
    "charging",
    "ignition",
    "turbo",
    "can_bus",
    "suspension",
    "differential",
)

RISK_WEIGHT = {"critical": 4, "high": 3, "medium": 2, "low": 1}

QUERY = """
SELECT
    c.id, c.code, c.context_key, c.category, c.context_type,
    m.name AS manufacturer,
    f.risk_level, f.mil, f.emissions_relevant, f.limp_mode_possible,
    (SELECT COUNT(*) FROM dtc_causes x WHERE x.dtc_code_id = c.id)   AS causes,
    (SELECT COUNT(*) FROM dtc_symptoms x WHERE x.dtc_code_id = c.id) AS symptoms,
    (SELECT COUNT(*) FROM dtc_repairs x WHERE x.dtc_code_id = c.id)  AS repairs,
    (SELECT COUNT(*) FROM dtc_tests x WHERE x.dtc_code_id = c.id)    AS tests,
    (SELECT COUNT(DISTINCT p.source_id) FROM provenance_claims p
      WHERE p.entity_type = 'dtc_code' AND p.entity_id = c.id)        AS sources,
    (SELECT COUNT(*) FROM dtc_codes c2 WHERE c2.code = c.code)        AS contexts,
    (SELECT COUNT(*) FROM conflicts k
      WHERE k.dtc_code_id = c.id AND k.status = 'needs_review')       AS open_conflicts,
    (SELECT COUNT(*) FROM conflicts k
      WHERE k.dtc_code_id = c.id AND k.status = 'needs_review'
        AND k.similarity < 0.75 AND f.risk_level IN ('high','critical')) AS critical_conflicts
FROM dtc_codes c
LEFT JOIN manufacturers m ON m.id = c.manufacturer_id
LEFT JOIN dtc_flags f ON f.dtc_code_id = c.id
"""


def component_keys(conn: sqlite3.Connection, dtc_code_id: int) -> list[str]:
    return [
        row[0]
        for row in conn.execute(
            "SELECT component_key FROM dtc_components WHERE dtc_code_id = ? ORDER BY component_key",
            (dtc_code_id,),
        )
    ]


def _matches(keys: Iterable[str], terms: Iterable[str]) -> list[str]:
    hits = []
    for key in keys:
        lowered = (key or "").lower()
        if any(term in lowered for term in terms):
            hits.append(key)
    return hits


def classify(row: dict[str, Any], components: list[str]) -> tuple[int, int, list[str]]:
    """Return (tier, score, reasons) for one identity."""
    reasons: list[str] = []
    score = 0

    risk = (row["risk_level"] or "").lower()
    score += RISK_WEIGHT.get(risk, 0)
    if risk:
        reasons.append(f"risk_level={risk} published by the source")
    if row["mil"]:
        score += 2
        reasons.append("MIL requested (dashboard warning)")
    if row["limp_mode_possible"]:
        score += 2
        reasons.append("limp mode possible")
    if row["emissions_relevant"]:
        score += 1
        reasons.append("emissions relevant")

    safety_hits = _matches(components, SAFETY_TERMS)
    vital_hits = _matches(components, VITAL_TERMS)
    if safety_hits:
        score += 5
        reasons.append(f"safety component(s): {', '.join(safety_hits[:4])}")
    if vital_hits:
        score += 2
        reasons.append(f"vital component(s): {', '.join(vital_hits[:4])}")

    sources = row["sources"] or 0
    contexts = row["contexts"] or 0
    score += min(sources, 3) + min(contexts, 5) / 2
    if sources:
        reasons.append(f"{sources} independent source(s) state this code")
    if contexts > 1:
        reasons.append(f"{contexts} manufacturer/generic contexts for the same code")

    if row["causes"]:
        reasons.append(f"{row['causes']} cause statement(s) available for review")
    if row["tests"]:
        reasons.append(f"{row['tests']} inspection test(s) available")
    if row["critical_conflicts"]:
        reasons.append(
            f"{row['critical_conflicts']} unresolved critical conflict(s) - do not publish before a human decides"
        )

    if safety_hits or (risk in ("high", "critical") and row["limp_mode_possible"]):
        tier = 1
    elif vital_hits or (row["category"] in ("powertrain", "chassis") and risk in ("high", "medium")):
        tier = 2
    elif sources >= 2 or contexts >= 3 or (risk in ("high", "medium") and row["causes"]):
        tier = 3
    else:
        tier = 4
    return tier, round(score, 2), reasons


def priority_index(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    rows = [dict(row) for row in conn.execute(QUERY)]
    components: dict[int, list[str]] = {}
    for dtc_id, key in conn.execute("SELECT dtc_code_id, component_key FROM dtc_components"):
        components.setdefault(dtc_id, []).append(key)

    index = []
    for row in rows:
        tier, score, reasons = classify(row, components.get(row["id"], []))
        index.append(
            {
                "dtc_code_id": row["id"],
                "code": row["code"],
                "context_key": row["context_key"],
                "context_type": row["context_type"],
                "manufacturer": row["manufacturer"],
                "category": row["category"],
                "tier": tier,
                "score": score,
                "reasons": reasons,
                "risk_level": row["risk_level"],
                "mil": row["mil"],
                "limp_mode_possible": row["limp_mode_possible"],
                "causes": row["causes"],
                "symptoms": row["symptoms"],
                "repairs": row["repairs"],
                "tests": row["tests"],
                "sources": row["sources"],
                "contexts": row["contexts"],
                "open_conflicts": row["open_conflicts"],
                "critical_conflicts": row["critical_conflicts"],
            }
        )
    index.sort(key=lambda e: (e["tier"], -e["score"], e["code"], e["context_key"]))
    return index


def summarise(index: list[dict[str, Any]]) -> dict[str, Any]:
    by_tier: dict[int, dict[str, Any]] = {}
    for tier, label in TIERS.items():
        entries = [e for e in index if e["tier"] == tier]
        by_tier[tier] = {
            "label": label,
            "identities": len(entries),
            "codes": len({e["code"] for e in entries}),
            "with_causes": sum(1 for e in entries if e["causes"]),
            "with_tests": sum(1 for e in entries if e["tests"]),
            "critical_conflicts": sum(1 for e in entries if e["critical_conflicts"]),
        }
    return {
        "identities": len(index),
        "codes": len({e["code"] for e in index}),
        "by_tier": by_tier,
        "prevalence_note": (
            "prevalence is a proxy: number of independent sources and manufacturer contexts, "
            "not measured workshop frequency"
        ),
    }


def write_index(index: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "code",
        "context_key",
        "context_type",
        "manufacturer",
        "category",
        "tier",
        "score",
        "risk_level",
        "mil",
        "limp_mode_possible",
        "causes",
        "symptoms",
        "repairs",
        "tests",
        "sources",
        "contexts",
        "open_conflicts",
        "critical_conflicts",
        "reasons",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for entry in index:
            row = dict(entry)
            row["reasons"] = " | ".join(entry["reasons"])
            writer.writerow(row)


def render_priority(index: list[dict[str, Any]], limit: int = 40) -> str:
    summary = summarise(index)
    lines = [
        "# Priority order for code review",
        "",
        f"{summary['identities']:,} identities / {summary['codes']:,} distinct codes ranked. "
        f"{summary['prevalence_note']}.",
        "",
        "| Tier | What it means | Identities | Codes | With causes | With tests | Critical conflicts |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for tier, label in TIERS.items():
        s = summary["by_tier"][tier]
        lines.append(
            f"| {tier} | {label} | {s['identities']:,} | {s['codes']:,} | {s['with_causes']:,} | "
            f"{s['with_tests']:,} | {s['critical_conflicts']:,} |"
        )
    lines += ["", f"## First {limit} entries", "", "| # | Code | Context | Tier | Score | Why |", "| --- | --- | --- | --- | --- | --- |"]
    for position, entry in enumerate(index[:limit], start=1):
        why = "; ".join(entry["reasons"][:3])
        lines.append(
            f"| {position} | {entry['code']} | {entry['context_key']} | {entry['tier']} | "
            f"{entry['score']} | {why} |"
        )
    lines.append("")
    return "\n".join(lines)
