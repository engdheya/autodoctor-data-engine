"""Export the check text the sources actually contain, with its scope and its caveats.

The engine never writes an inspection procedure. What it can do is quote, verbatim, the
sentences of a source that describe a check, say which vehicle or engine the source itself
names, and show whether the quoted sentence carries a measurement. Everything else - tools,
nominal values, limits, warnings - stays empty until a qualified technician writes it.

Guarantees enforced here and asserted in the tests:

* every quote is a verbatim substring of the stored description;
* any number that appears inside a quote is reported only as part of that quote;
* the scope of a procedure is either the identity's own context or a manufacturer/fuel term
  the source itself printed - never an inference.
"""

from __future__ import annotations

import csv
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

CHECK_WORDS = re.compile(
    r"\b(test|check|measure|swap|inspect|verify|probe|compare|monitor|read)\w*\b", re.IGNORECASE
)

MEASUREMENT = re.compile(
    r"\b\d+(?:[.,]\d+)?\s?(?:%|V|mV|A|mA|ohm|Ω|kΩ|bar|hPa|psi|kPa|°C|C|rpm|km/h|mm|s)\b"
)

FUEL_TERMS = ("diesel", "petrol", "gasoline", "benzine", "otto", "common rail", "gdi", "mpi")

CYLINDER_TERMS = re.compile(r"\b(?:V[6-8]|V10|V12|R4|R6|inline[- ]?[46]|[1-4]\.[0-9]\s?(?:TDI|TSI|HDi|dCi|CDI|TDCi))\b")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.;])\s+", text) if s.strip()]


def _scope(conn: sqlite3.Connection, dtc_id: int, context_type: str, description: str) -> dict[str, Any]:
    manufacturers = [row[0] for row in conn.execute("SELECT name FROM manufacturers ORDER BY name")]
    mentions: list[dict[str, str]] = []
    for sentence in _sentences(description):
        lowered = sentence.lower()
        for name in manufacturers:
            if len(name) >= 3 and re.search(rf"\b{re.escape(name.lower())}\b", lowered):
                mentions.append({"kind": "manufacturer", "term": name, "sentence": sentence})
        lowered_tokens = [t for t in FUEL_TERMS if t in lowered]
        for token in lowered_tokens:
            mentions.append({"kind": "fuel", "term": token, "sentence": sentence})
        for match in CYLINDER_TERMS.finditer(sentence):
            mentions.append({"kind": "engine", "term": match.group(0), "sentence": sentence})

    # De-duplicate on (kind, term, sentence) so a code with a long description stays readable.
    seen = set()
    unique = []
    for mention in mentions:
        key = (mention["kind"], mention["term"], mention["sentence"])
        if key not in seen:
            seen.add(key)
            unique.append(mention)

    if context_type == "generic":
        base = "SAE J2012 / ISO 15031-6 generic code: applies to every vehicle that reports it"
    else:
        manufacturer = conn.execute(
            "SELECT m.name FROM dtc_codes c JOIN manufacturers m ON m.id = c.manufacturer_id "
            "WHERE c.id = ?",
            (dtc_id,),
        ).fetchone()
        base = (
            f"manufacturer-specific definition ({manufacturer[0]})"
            if manufacturer and manufacturer[0]
            else "manufacturer-specific definition"
        )
    return {
        "identity_scope": base,
        "source_mentions": unique,
        "status": "source_text_mention" if unique else "not_stated",
        "note": (
            "Mentions are what the source printed, not a verified applicability list. A "
            "technician must confirm the procedure applies to the exact vehicle and engine."
        ),
    }


def build_entries(
    conn: sqlite3.Connection, index: list[dict[str, Any]], tiers: tuple[int, ...]
) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    entries: list[dict[str, Any]] = []
    without: list[dict[str, Any]] = []

    for entry in index:
        if entry["tier"] not in tiers:
            continue
        row = conn.execute(
            "SELECT title, description FROM dtc_definitions "
            "WHERE dtc_code_id = ? AND language = 'en' AND is_canonical = 1 LIMIT 1",
            (entry["dtc_code_id"],),
        ).fetchone()
        description = (row["description"] if row else "") or ""
        quotes = []
        for sentence in _sentences(description):
            if len(sentence) > 25 and CHECK_WORDS.search(sentence):
                quotes.append(
                    {
                        "text_en": sentence,
                        "verbatim": sentence in description,
                        "measurement_mentions": [
                            {"text": m.group(0)} for m in MEASUREMENT.finditer(sentence)
                        ],
                        "status": "quoted_unreviewed",
                    }
                )
        references = [
            {"url": r[0], "kind": r[1], "label": r[2]}
            for r in conn.execute(
                "SELECT url, kind, label FROM dtc_evidence_sources WHERE dtc_code_id = ? "
                "ORDER BY CASE kind WHEN 'reference' THEN 0 ELSE 1 END, url",
                (entry["dtc_code_id"],),
            )
        ]
        base = {
            "code": entry["code"],
            "context_key": entry["context_key"],
            "tier": entry["tier"],
            "title_en": row["title"] if row else None,
        }
        if quotes:
            entries.append(
                {
                    **base,
                    "quotes": quotes,
                    "scope": _scope(
                        conn, entry["dtc_code_id"], entry["context_type"], description
                    ),
                    "references": references,
                    "tools": [],
                    "nominal_values": [],
                    "limits": [],
                    "warnings": [],
                    "authoring_status": "quoted_only",
                    "approval_status": "not_approved",
                    "next_step": (
                        "A qualified technician writes the procedure (tools, nominal value, "
                        "limit, warning, applicability) against the quoted checks and references."
                    ),
                }
            )
        else:
            without.append(
                {
                    **base,
                    "references": references,
                    "reason": (
                        "the source cites references but contains no check sentence"
                        if references
                        else "no reference and no check text in the licensed sources"
                    ),
                    "approval_status": "no_source_text",
                }
            )

    with_quotes = len(entries)
    measurements = sum(1 for e in entries if any(q["measurement_mentions"] for q in e["quotes"]))
    return {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "tiers": list(tiers),
        "warning": (
            "Quoted source text only. No tool list, nominal value, limit or warning has been "
            "written by the engine, and nothing here is approved for use."
        ),
        "summary": {
            "codes_with_quotes": with_quotes,
            "codes_without_source_text": len(without),
            "quotes_total": sum(len(e["quotes"]) for e in entries),
            "quotes_with_measurement": measurements,
            "codes_with_scope_mentions": sum(
                1 for e in entries if e["scope"]["source_mentions"]
            ),
            "approved_procedures": 0,
        },
        "entries": entries,
        "without_source_text": without,
    }


def write_procedures(payload: dict[str, Any], out_dir: Path) -> tuple[Path, Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = out_dir / "procedures-quoted.yaml"
    csv_path = out_dir / "procedures-quoted.csv"
    md_path = out_dir / "procedures-quoted.md"

    yaml_path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "code",
                "tier",
                "title_en",
                "quotes",
                "has_measurement",
                "scope_identity",
                "scope_mentions",
                "references",
                "authoring_status",
                "approval_status",
            ]
        )
        for entry in payload["entries"]:
            writer.writerow(
                [
                    entry["code"],
                    entry["tier"],
                    entry["title_en"],
                    len(entry["quotes"]),
                    any(q["measurement_mentions"] for q in entry["quotes"]),
                    entry["scope"]["identity_scope"],
                    "; ".join(m["term"] for m in entry["scope"]["source_mentions"]),
                    "; ".join(r["url"] for r in entry["references"]),
                    entry["authoring_status"],
                    entry["approval_status"],
                ]
            )

    s = payload["summary"]
    md = [
        "# Quoted check text — tiers " + ", ".join(str(t) for t in payload["tiers"]),
        "",
        payload["warning"],
        "",
        "| Measure | Count |",
        "| --- | --- |",
        f"| Codes with quoted check text | {s['codes_with_quotes']:,} |",
        f"| Codes without any check text in the sources | {s['codes_without_source_text']:,} |",
        f"| Verbatim quotes | {s['quotes_total']:,} |",
        f"| Quotes that mention a measurement | {s['quotes_with_measurement']:,} |",
        f"| Codes where the source names a vehicle/engine term | {s['codes_with_scope_mentions']:,} |",
        f"| Approved procedures | {s['approved_procedures']} |",
        "",
        "Every quote is a verbatim substring of the stored English description; numbers appear "
        "only inside those quotes and are not validated by the engine.",
        "",
        "## First entries",
        "",
        "| Code | Tier | Quote | Scope |",
        "| --- | --- | --- | --- |",
    ]
    for entry in payload["entries"][:40]:
        first = entry["quotes"][0]["text_en"].replace("|", "/")[:160]
        mentions = ", ".join(m["term"] for m in entry["scope"]["source_mentions"]) or "-"
        md.append(f"| {entry['code']} | {entry['tier']} | {first} | {mentions} |")
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return yaml_path, csv_path, md_path


def verify_no_invention(payload: dict[str, Any], descriptions: dict[str, str]) -> list[str]:
    """Return the list of integrity problems; empty means every quote is verbatim."""
    problems: list[str] = []
    for entry in payload["entries"]:
        if entry["tools"] or entry["nominal_values"] or entry["limits"] or entry["warnings"]:
            problems.append(f"{entry['code']}: engine wrote a procedure field")
        description = descriptions.get(entry["context_key"], "")
        for quote in entry["quotes"]:
            if quote["text_en"] not in description:
                problems.append(f"{entry['code']}: quote is not verbatim")
    return problems
