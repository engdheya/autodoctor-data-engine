"""Triage every conflict into an auditable review band - without deciding anything.

The engine never picks a winner. What it *can* do is tell a human which of the
open conflicts could hurt a user if left unreviewed, and why, using only
measurable features: the context of the code, the risk level of the code, how far
apart the statements are, and which sources disagree.

Rules are deliberately few and documented, because a reviewer has to be able to
argue with them:

===================  ================================================================
band                 rule
===================  ================================================================
``critical``         generic (SAE) code, risk ``high``/``critical``, statements
                     less than 75 % similar -> a user could read the wrong meaning
                     for a safety-relevant fault
``high``             any other generic code -> the meaning most users will see
``medium``           manufacturer / ECU / vehicle context, similarity < 85 %
``low``              manufacturer / ECU / vehicle context, similarity >= 85 %
                     (wording variants - candidates for ``retained_as_alternatives``)
===================  ================================================================

Nothing here writes a decision. ``status`` stays ``needs_review``; the report is an
*order of work*, and the review store (``reviews.py``) is still the only place a
judgement is recorded.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

BANDS = ("critical", "high", "medium", "low")

#: thresholds, in one place so the report and the tests cannot drift
CRITICAL_SIMILARITY = 0.75
VARIANT_SIMILARITY = 0.85
RISK_LEVELS = ("high", "critical")


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class TriageRow:
    conflict_id: int
    fingerprint: str
    code: str
    context_key: str
    context_type: str
    conflict_type: str
    attribute: str
    similarity: float | None
    risk_level: str | None
    manufacturer: str | None
    sources: list[str]
    summary: str
    band: str
    reason: str
    statements: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "conflict_id": self.conflict_id,
            "fingerprint": self.fingerprint,
            "code": self.code,
            "context_key": self.context_key,
            "context_type": self.context_type,
            "conflict_type": self.conflict_type,
            "attribute": self.attribute,
            "similarity": self.similarity,
            "risk_level": self.risk_level,
            "manufacturer": self.manufacturer,
            "sources": self.sources,
            "band": self.band,
            "reason": self.reason,
            "summary": self.summary,
        }
        if self.statements:
            payload["statements"] = self.statements
        return payload


def _band(context_type: str, risk: str | None, similarity: float | None) -> tuple[str, str]:
    sim = similarity if similarity is not None else 0.0
    if context_type == "generic":
        if risk in RISK_LEVELS and sim < CRITICAL_SIMILARITY:
            return "critical", (
                f"generic code with risk '{risk}' whose statements agree only {sim:.0%}: "
                "publishing it unreviewed shows the user a possibly wrong meaning for a "
                "safety-relevant fault"
            )
        return "high", (
            "generic code: this is the definition most users will see, so it is reviewed "
            "before any manufacturer-specific one"
        )
    if sim >= VARIANT_SIMILARITY:
        return "low", (
            f"context-specific statements that are {sim:.0%} similar: most likely wording "
            "variants. A reviewer may mark them 'retained_as_alternatives' - the engine "
            "will not do it unattended"
        )
    return "medium", (
        f"context-specific statements that differ materially ({sim:.0%} similar); the "
        "difference may be real (model, year, ECU), so it stays open until reviewed"
    )


def triage_conflicts(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT c.id, c.fingerprint, c.code, c.context_key, c.conflict_type, c.attribute,
               c.summary, c.similarity, c.status,
               k.context_type, m.name AS manufacturer, f.risk_level
        FROM conflicts c
        LEFT JOIN dtc_codes k ON k.id = c.dtc_code_id
        LEFT JOIN manufacturers m ON m.id = k.manufacturer_id
        LEFT JOIN dtc_flags f ON f.dtc_code_id = c.dtc_code_id
        ORDER BY c.id
        """
    ).fetchall()

    evidence: dict[int, list[dict[str, Any]]] = {}
    for row in conn.execute(
        "SELECT conflict_id, source_slug, value_text FROM conflict_evidence ORDER BY id"
    ):
        evidence.setdefault(int(row[0]), []).append(
            {"source": row[1], "value": row[2]}
        )

    triaged: list[TriageRow] = []
    for row in rows:
        statements = evidence.get(int(row["id"]), [])
        sources = sorted({str(s["source"]) for s in statements})
        context_type = str(row["context_type"] or "unknown")
        similarity = float(row["similarity"]) if row["similarity"] is not None else None
        band, reason = _band(context_type, row["risk_level"], similarity)
        triaged.append(
            TriageRow(
                conflict_id=int(row["id"]),
                fingerprint=str(row["fingerprint"]),
                code=str(row["code"]),
                context_key=str(row["context_key"]),
                context_type=context_type,
                conflict_type=str(row["conflict_type"]),
                attribute=str(row["attribute"]),
                similarity=similarity,
                risk_level=row["risk_level"],
                manufacturer=row["manufacturer"],
                sources=sources,
                summary=str(row["summary"] or ""),
                band=band,
                reason=reason,
                statements=statements,
            )
        )

    by_band = {band: 0 for band in BANDS}
    by_context: dict[str, int] = {}
    by_risk: dict[str, int] = {}
    by_pair: dict[str, int] = {}
    buckets = {"0-25%": 0, "25-50%": 0, "50-75%": 0, "75-90%": 0, "90-100%": 0}
    for item in triaged:
        by_band[item.band] += 1
        by_context[item.context_type] = by_context.get(item.context_type, 0) + 1
        by_risk[item.risk_level or "unknown"] = by_risk.get(item.risk_level or "unknown", 0) + 1
        if item.sources:
            by_pair[" + ".join(item.sources)] = by_pair.get(" + ".join(item.sources), 0) + 1
        sim = item.similarity or 0.0
        key = (
            "0-25%" if sim < 0.25
            else "25-50%" if sim < 0.5
            else "50-75%" if sim < 0.75
            else "75-90%" if sim < 0.9
            else "90-100%"
        )
        buckets[key] += 1

    return {
        "generated_at": _now(),
        "rules": {
            "critical_similarity": CRITICAL_SIMILARITY,
            "variant_similarity": VARIANT_SIMILARITY,
            "risk_levels": list(RISK_LEVELS),
        },
        "totals": {"conflicts": len(triaged), "by_band": by_band},
        "by_context": by_context,
        "by_risk": by_risk,
        "by_source_pair": dict(sorted(by_pair.items(), key=lambda kv: -kv[1])),
        "by_similarity": buckets,
        "items": [item.to_dict() for item in triaged],
    }


def render_triage_markdown(report: dict[str, Any], *, sample: int = 15) -> str:
    totals = report["totals"]
    items = report["items"]
    lines: list[str] = []
    add = lines.append
    add("# Conflict triage")
    add("")
    add(f"Generated: {report['generated_at']}")
    add("")
    add("Triage is an **order of work**, not a decision. Every conflict below is still")
    add("`needs_review` and both statements are still shipped; nothing is chosen here. The only")
    add("place a judgement is recorded is `data/reviews/conflicts.yaml`.")
    add("")
    add("## Rules")
    add("")
    add(f"* `critical` - generic code, risk in {report['rules']['risk_levels']}, similarity "
        f"< {report['rules']['critical_similarity']:.0%}")
    add("* `high` - any other generic code")
    add(f"* `medium` - manufacturer/ECU/vehicle context, similarity "
        f"< {report['rules']['variant_similarity']:.0%}")
    add(f"* `low` - manufacturer/ECU/vehicle context, similarity "
        f">= {report['rules']['variant_similarity']:.0%} (wording variants)")
    add("")
    add("## Counts")
    add("")
    add("| Band | Conflicts |")
    add("| --- | ---: |")
    for band in BANDS:
        add(f"| {band} | {totals['by_band'][band]:,} |")
    add(f"| **total** | **{totals['conflicts']:,}** |")
    add("")
    add("By context: " + ", ".join(f"`{k}` {v:,}" for k, v in sorted(
        report["by_context"].items(), key=lambda kv: -kv[1])))
    add("")
    add("By risk level of the code: " + ", ".join(
        f"`{k}` {v:,}" for k, v in sorted(report["by_risk"].items(), key=lambda kv: -kv[1])))
    add("")
    add("By source pair: " + ", ".join(
        f"`{k}` {v:,}" for k, v in report["by_source_pair"].items()))
    add("")
    add("By statement similarity: " + ", ".join(f"`{k}` {v:,}" for k, v in report["by_similarity"].items()))
    add("")
    for band in BANDS:
        batch = [item for item in items if item["band"] == band]
        if not batch:
            continue
        add(f"## {band} batch - {len(batch):,} conflicts")
        add("")
        add("| Code | Context | Similarity | Risk | Sources | Conflict |")
        add("| --- | --- | ---: | --- | --- | --- |")
        for item in batch[:sample]:
            similarity = "-" if item["similarity"] is None else f"{item['similarity']:.0%}"
            add(
                f"| {item['code']} | {item['context_type']} | {similarity} "
                f"| {item['risk_level'] or '-'} | {', '.join(item['sources'])} | "
                f"`{item['fingerprint']}` |"
            )
        if len(batch) > sample:
            add(f"| … | | | | | {len(batch) - sample:,} more in the JSON |")
        add("")
        add(f"_Why this band:_ {batch[0]['reason']}")
        add("")
    add("## What publishing an unreviewed conflict does")
    add("")
    add("* the conflict stays in the bundle (`v_dtc_conflicts`) with both statements;")
    add("* both statements keep `verification_status = 'conflicting'`;")
    add("* the client must show the disagreement, never a single chosen meaning;")
    add("* the release notes must quote the open count per band.")
    add("")
    return "\n".join(lines)


def write_triage(conn: sqlite3.Connection, reports_dir) -> tuple[Any, Any]:
    import json
    from pathlib import Path

    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    report = triage_conflicts(conn)
    json_path = reports_dir / "conflict-triage.json"
    md_path = reports_dir / "conflict-triage.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_triage_markdown(report) + "\n", encoding="utf-8")
    return json_path, md_path


__all__ = [
    "BANDS",
    "CRITICAL_SIMILARITY",
    "VARIANT_SIMILARITY",
    "triage_conflicts",
    "render_triage_markdown",
    "write_triage",
]
