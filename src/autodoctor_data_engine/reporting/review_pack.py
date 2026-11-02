"""Build human review packs for a priority slice of the database.

A pack is a review document, not a product: every fact carries the source that stated it and
the status that fact has in the database, machine-drafted Arabic is labelled as such, and no
inspection step or measurement value is ever generated. Where the licensed sources contain no
step list the pack says so and links the reference the source itself cited.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

CHECK_WORDS = re.compile(
    r"\b(test|check|measure|swap|inspect|verify|probe|compare)\w*\b", re.IGNORECASE
)

STATUS = {
    "reviewed": "approved by a named human reviewer",
    "machine_draft": "machine draft, never shown to a user as approved",
    "source_reported": "as published by the source, not independently verified",
    "verified": "source states it and provenance is complete",
}


def load_arabic(path: Path | None) -> dict[str, dict[str, Any]]:
    """Read translation drafts in the engine's own translation-file format.

    The same file can later be signed off and ingested by ``build-db``; nothing here invents
    a status, it only reports what the file says.
    """
    if path is None or not path.is_file():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if isinstance(payload, dict):
        payload = payload.get("codes", [])
    return {entry["code"]: entry for entry in payload if entry.get("code")}


def load_arabic_files(paths: list[Path]) -> dict[str, dict[str, Any]]:
    """Merge several translation draft files; a later file overrides an earlier one."""
    merged: dict[str, dict[str, Any]] = {}
    for path in paths:
        merged.update(load_arabic(path))
    return merged


def _fact_sources(conn: sqlite3.Connection, entity_type: str, ids: list[int]) -> dict[int, list[str]]:
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"""
        SELECT p.entity_id, s.slug
        FROM provenance_claims p
        JOIN data_sources s ON s.id = p.source_id
        WHERE p.entity_type = ? AND p.entity_id IN ({placeholders})
        """,
        (entity_type, *ids),
    ).fetchall()
    result: dict[int, list[str]] = {}
    for entity_id, slug in rows:
        result.setdefault(entity_id, []).append(slug)
    return result


def _definition(conn: sqlite3.Connection, dtc_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, title, description, verification_status
        FROM dtc_definitions
        WHERE dtc_code_id = ? AND language = 'en' AND is_canonical = 1
        LIMIT 1
        """,
        (dtc_id,),
    ).fetchone()
    if row is None:
        return None
    sources = _fact_sources(conn, "dtc_definition", [row[0]]).get(row[0], [])
    return {
        "title_en": row[1],
        "description_en": row[2],
        "verification_status": row[3],
        "sources": sorted(set(sources)),
    }


def _causes(conn: sqlite3.Connection, dtc_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT c.id, t.label, c.likelihood
        FROM dtc_causes c
        JOIN dtc_cause_texts t ON t.cause_id = c.id AND t.language = 'en'
        WHERE c.dtc_code_id = ?
        ORDER BY CASE c.likelihood WHEN 'high' THEN 0 WHEN 'medium' THEN 1
                                  WHEN 'low' THEN 2 ELSE 3 END
        """,
        (dtc_id,),
    ).fetchall()
    sources = _fact_sources(conn, "dtc_cause", [r[0] for r in rows])
    return [
        {
            "text_en": r[1],
            "likelihood": r[2],
            "source": ", ".join(sorted(set(sources.get(r[0], [])))) or "unattributed",
            "review_status": "source_reported",
        }
        for r in rows
    ]


def _symptoms(conn: sqlite3.Connection, dtc_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT s.id, t.text
        FROM dtc_symptoms s
        JOIN dtc_symptom_texts t ON t.symptom_id = s.id AND t.language = 'en'
        WHERE s.dtc_code_id = ?
        ORDER BY s.id
        """,
        (dtc_id,),
    ).fetchall()
    sources = _fact_sources(conn, "dtc_symptom", [r[0] for r in rows])
    return [
        {
            "text_en": r[1],
            "source": ", ".join(sorted(set(sources.get(r[0], [])))) or "unattributed",
            "review_status": "source_reported",
        }
        for r in rows
    ]


def _repairs(conn: sqlite3.Connection, dtc_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT r.id, t.text, r.difficulty, r.diy_possible, r.cost_min, r.cost_max,
               r.currency, r.hours_min, r.hours_max
        FROM dtc_repairs r
        JOIN dtc_repair_texts t ON t.repair_id = r.id AND t.language = 'en'
        WHERE r.dtc_code_id = ?
        ORDER BY r.id
        """,
        (dtc_id,),
    ).fetchall()
    sources = _fact_sources(conn, "dtc_repair", [r[0] for r in rows])
    return [
        {
            "text_en": r[1],
            "difficulty": r[2],
            "diy_possible": bool(r[3]) if r[3] is not None else None,
            "cost_range": [r[4], r[5]] if r[4] is not None or r[5] is not None else None,
            "currency": r[6],
            "hours_range": [r[7], r[8]] if r[7] is not None or r[8] is not None else None,
            "source": ", ".join(sorted(set(sources.get(r[0], [])))) or "unattributed",
            "review_status": "source_reported",
        }
        for r in rows
    ]


def _procedure(conn: sqlite3.Connection, dtc_id: int, description: str | None) -> dict[str, Any]:
    references = [
        {"url": row[0], "kind": row[1], "label": row[2]}
        for row in conn.execute(
            "SELECT url, kind, label FROM dtc_evidence_sources WHERE dtc_code_id = ? "
            "ORDER BY CASE kind WHEN 'reference' THEN 0 ELSE 1 END, url",
            (dtc_id,),
        )
    ]
    quoted = []
    if description:
        for sentence in re.split(r"(?<=[.;])\s+", description):
            if len(sentence) > 25 and CHECK_WORDS.search(sentence):
                quoted.append(sentence.strip())
    steps = [
        {"text_en": sentence, "source": "obdex description", "review_status": "source_reported"}
        for sentence in quoted[:5]
    ]
    if steps:
        status = "draft_unreviewed"
        note = (
            "Verbatim sentences from the source description that describe a check. They are "
            "not a procedure: no tool list, no nominal value and no limit may be added until a "
            "qualified technician approves a written procedure."
        )
    elif references:
        status = "needs_written_procedure"
        note = (
            "The source cites references but contains no step list. A technician must write "
            "the procedure against these references; nothing is generated here."
        )
    else:
        status = "no_reference_found"
        note = "No reference in the licensed sources; this code cannot get a procedure yet."
    return {
        "status": status,
        "note": note,
        "quoted_checks": steps,
        "references": references,
        "tools": [],
        "nominal_values": [],
        "review_status": "unreviewed_draft" if steps else "not_started",
    }


def _conflicts(conn: sqlite3.Connection, dtc_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT fingerprint, conflict_type, similarity, status, summary
        FROM conflicts WHERE dtc_code_id = ?
        ORDER BY similarity
        """,
        (dtc_id,),
    ).fetchall()
    return [
        {
            "fingerprint": r[0],
            "type": r[1],
            "similarity": r[2],
            "status": r[3],
            "summary": r[4],
        }
        for r in rows
    ]


def _arabic_status(draft: dict[str, Any]) -> str:
    if not draft:
        return "not_authored"
    if draft.get("reviewed") and draft.get("reviewer"):
        return "reviewed"
    return "machine_draft"


def _safety_note(flags: dict[str, Any], components: list[str]) -> str:
    parts = []
    if flags.get("limp_mode_possible"):
        parts.append("source states limp mode is possible")
    if flags.get("mil"):
        parts.append("requests the dashboard warning lamp")
    if flags.get("emissions_relevant"):
        parts.append("emissions relevant")
    if components:
        parts.append(f"components: {', '.join(components[:5])}")
    return "; ".join(parts)


def build_pack(
    conn: sqlite3.Connection,
    index: list[dict[str, Any]],
    arabic: dict[str, dict[str, Any]],
    tier: int,
    limit: int,
) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    selected = [entry for entry in index if entry["tier"] == tier][:limit]
    entries = []
    for position, entry in enumerate(selected, start=1):
        dtc_id = entry["dtc_code_id"]
        definition = _definition(conn, dtc_id) or {}
        components = [
            row[0]
            for row in conn.execute(
                "SELECT component_key FROM dtc_components WHERE dtc_code_id = ? ORDER BY 1",
                (dtc_id,),
            )
        ]
        flags = {
            "risk_level": entry["risk_level"],
            "mil": entry["mil"],
            "emissions_relevant": None,
            "limp_mode_possible": entry["limp_mode_possible"],
        }
        row = conn.execute(
            "SELECT emissions_relevant FROM dtc_flags WHERE dtc_code_id = ?", (dtc_id,)
        ).fetchone()
        if row:
            flags["emissions_relevant"] = bool(row[0])
        draft = arabic.get(entry["code"], {})
        entries.append(
            {
                "priority_position": position,
                "code": entry["code"],
                "context_key": entry["context_key"],
                "context_type": entry["context_type"],
                "manufacturer": entry["manufacturer"],
                "category": entry["category"],
                "tier": tier,
                "score": entry["score"],
                "why_here": entry["reasons"],
                "english": definition,
                "arabic_draft": {
                    "title_ar": draft.get("title"),
                    "description_ar": draft.get("description"),
                    "translator": draft.get("translator") or None,
                    "reviewer": draft.get("reviewer") or None,
                    "status": _arabic_status(draft),
                    "note": STATUS.get(_arabic_status(draft), ""),
                },
                "causes": _causes(conn, dtc_id),
                "symptoms": _symptoms(conn, dtc_id),
                "repairs": _repairs(conn, dtc_id),
                "severity": {
                    **flags,
                    "safety_note_en": _safety_note(flags, components),
                    "review_status": "source_reported",
                },
                "procedure": _procedure(conn, dtc_id, definition.get("description_en")),
                "conflicts": _conflicts(conn, dtc_id),
                "review_checklist": {
                    "english_text": "pending",
                    "arabic_text": "pending",
                    "procedure": "pending" if not _procedure(conn, dtc_id, definition.get("description_en"))["quoted_checks"] else "draft_ready",
                    "conflicts": "pending" if any(c["status"] == "needs_review" for c in _conflicts(conn, dtc_id)) else "clear",
                },
            }
        )
    ready = sum(1 for e in entries if e["arabic_draft"]["status"] == "machine_draft")
    with_steps = sum(1 for e in entries if e["procedure"]["quoted_checks"])
    return {
        "pack": f"tier{tier}-{datetime.now(UTC).strftime('%Y%m%d')}",
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "tier": tier,
        "limit": limit,
        "warning": (
            "Review material only. Nothing in this file is approved content, no conflict is "
            "resolved here, and no inspection value or tool list has been invented."
        ),
        "summary": {
            "entries": len(entries),
            "arabic_drafts": ready,
            "arabic_missing": len(entries) - ready,
            "entries_with_quoted_checks": with_steps,
            "entries_with_references": sum(1 for e in entries if e["procedure"]["references"]),
            "entries_without_reference": sum(
                1 for e in entries if e["procedure"]["status"] == "no_reference_found"
            ),
            "entries_with_open_conflicts": sum(
                1 for e in entries if any(c["status"] == "needs_review" for c in e["conflicts"])
            ),
        },
        "entries": entries,
    }


def write_pack(pack: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(pack, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )


def render_pack_markdown(packs: list[dict[str, Any]]) -> str:
    lines = [
        "# Priority review packs",
        "",
        "Generated from the built database. Each entry carries the English source text, the",
        "machine Arabic draft, the facts with the source that stated them, the safety flags and",
        "the procedure status. **Nothing here is approved content.**",
        "",
        "| Pack | Tier | Entries | Arabic drafts | With quoted checks | With references | No reference | Open conflicts |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for pack in packs:
        s = pack["summary"]
        lines.append(
            f"| {pack['pack']} | {pack['tier']} | {s['entries']} | {s['arabic_drafts']} | "
            f"{s['entries_with_quoted_checks']} | {s['entries_with_references']} | "
            f"{s['entries_without_reference']} | {s['entries_with_open_conflicts']} |"
        )
    lines.append("")
    return "\n".join(lines)
