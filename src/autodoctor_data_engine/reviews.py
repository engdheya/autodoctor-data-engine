"""Human review of conflicts, persisted across builds.

The engine never decides which source is right. When a reviewer does decide, the
decision must:

1. survive a rebuild (so a reviewed conflict does not reappear as open),
2. stay auditable (who decided, when, and why),
3. be re-applied by *content*, not by database id - ids change every build.

That is what this module is for. Decisions live in ``data/reviews/conflicts.yaml``
(committed, human editable), keyed by a fingerprint computed from the conflict
itself:

    sha256(version | type | context_key | attribute | sorted(slug:content_hash))

A conflict whose statements changed upstream gets a new fingerprint and therefore
needs a fresh review - a decision is never silently stretched over different text.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .config import Settings
from .conflict_resolution.detector import Conflict
from .utils.hashing import sha256_text
from .utils.textsim import canonical_form

FINGERPRINT_VERSION = "1"
DECISIONS = ("accepted_difference", "resolved")


class ReviewError(ValueError):
    """Raised when a review decision is incomplete or refers to nothing."""


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _statement_key(evidence) -> str:
    """Identify one side of a conflict by what it says, not by its row id."""
    if getattr(evidence, "content_hash", None):
        return f"{evidence.source_slug}:{evidence.content_hash}"
    return f"{evidence.source_slug}:{canonical_form(evidence.value)}"


def conflict_fingerprint(conflict: Conflict) -> str:
    parts = [
        FINGERPRINT_VERSION,
        conflict.conflict_type,
        conflict.context_key,
        conflict.attribute,
        *sorted(_statement_key(evidence) for evidence in conflict.evidence),
    ]
    return sha256_text("\n".join(parts))[:16]


@dataclass
class ReviewDecision:
    fingerprint: str
    decision: str
    note: str
    reviewer: str
    decided_at: str
    code: str | None = None
    context_key: str | None = None
    conflict_type: str | None = None
    chosen_source: str | None = None

    def __post_init__(self) -> None:
        if self.decision not in DECISIONS:
            raise ReviewError(
                f"decision must be one of {', '.join(DECISIONS)} (got {self.decision!r})"
            )
        if not (self.note or "").strip():
            raise ReviewError("a review decision needs a note explaining it")
        if not (self.reviewer or "").strip():
            raise ReviewError("a review decision needs a reviewer")
        if self.decision == "resolved" and not self.chosen_source:
            raise ReviewError("a 'resolved' decision must name the source it chose")

    @property
    def status(self) -> str:
        """The conflicts.status this decision writes."""
        return "accepted_difference" if self.decision == "accepted_difference" else "resolved"

    def resolution_note(self) -> str:
        chosen = f"; chose {self.chosen_source}" if self.chosen_source else ""
        return f"{self.decision}: {self.note.strip()}{chosen} (reviewer: {self.reviewer}, {self.decided_at})"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value not in (None, "")}


@dataclass
class ReviewStore:
    """Reads and writes ``data/reviews/conflicts.yaml``."""

    root: Path
    decisions: dict[str, ReviewDecision] = field(default_factory=dict)

    @classmethod
    def for_settings(cls, settings: Settings) -> ReviewStore:
        return cls(root=settings.root)

    @property
    def path(self) -> Path:
        return self.root / "data" / "reviews" / "conflicts.yaml"

    @classmethod
    def load(cls, root: Path) -> ReviewStore:
        store = cls(root=root)
        if not store.path.is_file():
            return store
        data = yaml.safe_load(store.path.read_text(encoding="utf-8")) or {}
        entries = data.get("decisions") if isinstance(data, dict) else data
        for entry in entries or []:
            if not isinstance(entry, dict) or not entry.get("fingerprint"):
                continue
            try:
                decision = ReviewDecision(**entry)
            except (ReviewError, TypeError):
                # a malformed row is ignored here and surfaced by `list-conflicts`
                continue
            store.decisions[decision.fingerprint] = decision
        return store

    def get(self, fingerprint: str) -> ReviewDecision | None:
        return self.decisions.get(fingerprint)

    def record(
        self,
        *,
        fingerprint: str,
        decision: str,
        note: str,
        reviewer: str,
        chosen_source: str | None = None,
        code: str | None = None,
        context_key: str | None = None,
        conflict_type: str | None = None,
    ) -> ReviewDecision:
        entry = ReviewDecision(
            fingerprint=fingerprint,
            decision=decision,
            note=note,
            reviewer=reviewer,
            decided_at=_now(),
            code=code,
            context_key=context_key,
            conflict_type=conflict_type,
            chosen_source=chosen_source,
        )
        self.decisions[entry.fingerprint] = entry
        self.save()
        return entry

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "note": (
                "Human review decisions for source conflicts. Keyed by a content fingerprint; "
                "see src/autodoctor_data_engine/reviews.py. Applied on every build."
            ),
            "decisions": [
                decision.to_dict() for decision in sorted(
                    self.decisions.values(), key=lambda d: d.decided_at
                )
            ],
        }
        self.path.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=100),
            encoding="utf-8",
        )
        return self.path

    # ------------------------------------------------------------------
    # build integration
    # ------------------------------------------------------------------
    def apply(self, conn, decisions: Iterable[ReviewDecision] | None = None) -> dict[str, int]:
        """Write decisions onto already-inserted conflict rows."""
        stats = {"applied": 0, "canonical_overrides": 0, "unmatched": 0}
        for decision in decisions if decisions is not None else self.decisions.values():
            row = conn.execute(
                "SELECT id, code, context_key, dtc_code_id FROM conflicts WHERE fingerprint = ?",
                (decision.fingerprint,),
            ).fetchone()
            if row is None:
                stats["unmatched"] += 1
                continue
            conn.execute(
                "UPDATE conflicts SET status = ?, resolution_note = ? WHERE id = ?",
                (decision.status, decision.resolution_note(), int(row["id"])),
            )
            stats["applied"] += 1
            if decision.chosen_source:
                stats["canonical_overrides"] += _apply_canonical_choice(
                    conn, decision, int(row["dtc_code_id"] or 0), row["context_key"]
                )
        return stats


def _apply_canonical_choice(conn, decision: ReviewDecision, code_id: int, context_key: str) -> int:
    """Make the reviewed statement the canonical one for its (code, language).

    The decision is about a language-specific statement, so the language is taken
    from the evidence that belongs to the chosen source.
    """
    if not code_id:
        return 0
    languages = {
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT language FROM dtc_definitions WHERE dtc_code_id = ?", (code_id,)
        )
    }
    updated = 0
    for language in sorted(filter(None, languages)):
        candidates = conn.execute(
            """
            SELECT d.id, d.content_hash FROM dtc_definitions d
            JOIN provenance_claims p
              ON p.entity_type = 'dtc_definition' AND p.entity_id = d.id
            JOIN data_sources s ON s.id = p.source_id
            WHERE d.dtc_code_id = ? AND d.language = ? AND s.slug = ?
            GROUP BY d.id
            """,
            (code_id, language, decision.chosen_source),
        ).fetchall()
        if len(candidates) != 1:
            # ambiguous (or absent) - leave the deterministic precedence choice alone
            continue
        conn.execute(
            "UPDATE dtc_definitions SET is_canonical = 0 WHERE dtc_code_id = ? AND language = ?",
            (code_id, language),
        )
        conn.execute(
            "UPDATE dtc_definitions SET is_canonical = 1 WHERE id = ?", (int(candidates[0][0]),)
        )
        updated += 1
    return updated
