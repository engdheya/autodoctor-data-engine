"""Materialise the client-facing content tables (schema 4).

Everything written here already exists in the database or in the repository's own
review files. The module deliberately contains no diagnostic content of its own:

* ``source_quotes`` — sentences cut from ``dtc_definitions.description`` with the same
  classifier the review exports use (``procedures.classify_sentences``), so a quote can
  never be categorised one way in the app and another way in the audit pack.
* ``procedure_scope`` — the scope caveats that accompany those quotes. Every row says
  ``applicability = 'unverified'`` and ``approval_status = 'not_approved'`` because no
  technician has signed a procedure off. The client is not allowed to relabel them.
* ``translation_drafts`` — the Arabic files under ``data/translations`` that a human has
  **not** reviewed. They are stored with ``reviewed = 0`` so the app can show them as
  drafts, never as approved content.
* ``dtc_priority`` — the tier and score from the documented ranking rules, frozen at build
  time because the mobile bundle does not carry the provenance matrix the ranking needs.

The build fails if a quoted sentence is not a verbatim substring of the source text, if a
quote has no category, or if a draft claims to be reviewed.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from ..reporting.priority import priority_index
from ..reporting.procedures import classify_sentences, scope_for
from ..translations import TranslationEntry

MIN_QUOTE_LENGTH = 25


class AppContentError(RuntimeError):
    """Raised when the derived content would misrepresent its provenance."""


def populate_app_content(
    conn: sqlite3.Connection,
    translations: list[TranslationEntry] | None = None,
) -> dict[str, Any]:
    """Fill the four client tables; return counts plus warnings."""
    warnings: list[str] = []
    quotes = _populate_quotes(conn, warnings)
    drafts = _populate_drafts(conn, translations or [], warnings)
    priority = _populate_priority(conn)
    _verify(conn)
    return {"source_quotes": quotes, "translation_drafts": drafts, "priority": priority, "warnings": warnings}


def _populate_quotes(conn: sqlite3.Connection, warnings: list[str]) -> int:
    conn.row_factory = sqlite3.Row
    conn.execute("DELETE FROM source_quotes")
    conn.execute("DELETE FROM procedure_scope")
    inserted = 0
    for row in conn.execute(
        """
        SELECT c.id, c.context_type, d.description
        FROM dtc_codes c
        JOIN dtc_definitions d
          ON d.dtc_code_id = c.id AND d.language = 'en' AND d.is_canonical = 1
        ORDER BY c.id
        """
    ):
        description = row["description"] or ""
        quotes = classify_sentences(description, min_length=MIN_QUOTE_LENGTH)
        if not quotes:
            continue
        for ordinal, quote in enumerate(quotes, start=1):
            # The classifier already checked this; assert it again so a future change to
            # either helper cannot silently ship a paraphrase as if it were quoted.
            if quote["text_en"] not in description:
                raise AppContentError(
                    f"dtc_code {row['id']}: quote {quote['text_en'][:60]!r} is not verbatim"
                )
            conn.execute(
                """
                INSERT INTO source_quotes (dtc_code_id, ordinal, text_en, category,
                    classification_rule, classification_status, verbatim, measurements_json,
                    quote_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    ordinal,
                    quote["text_en"],
                    quote["category"],
                    quote["classification"]["rule"],
                    quote["classification"]["status"],
                    1,
                    json.dumps(quote["measurement_mentions"], ensure_ascii=False)
                    if quote["measurement_mentions"]
                    else None,
                    quote["status"],
                ),
            )
            inserted += 1

        scope = scope_for(conn, row["id"], row["context_type"], description)
        conn.execute(
            """
            INSERT INTO procedure_scope (dtc_code_id, definition_scope, applicability,
                applicability_note, mentions_json, approval_status, authoring_status, next_step)
            VALUES (?, ?, 'unverified', ?, ?, 'not_approved', 'quoted_only', ?)
            """,
            (
                row["id"],
                scope["dtc_definition_scope"],
                scope["applicability_note"],
                # the sentence itself is already in source_quotes; keeping only the
                # term keeps this table small on the phone
                json.dumps(
                    [
                        {"kind": m["kind"], "term": m["term"]}
                        for m in scope["source_mentions"]
                    ],
                    ensure_ascii=False,
                )
                if scope["source_mentions"]
                else None,
                "A qualified technician writes the procedure (tools, nominal value, limit, "
                "warning, applicability) against the quoted checks and references.",
            ),
        )
    if inserted == 0:
        warnings.append("no source quotes were derived from the definitions")
    conn.commit()
    return inserted


def _populate_drafts(
    conn: sqlite3.Connection,
    translations: list[TranslationEntry],
    warnings: list[str],
) -> int:
    conn.execute("DELETE FROM translation_drafts")
    inserted = 0
    seen: set[tuple[str, str]] = set()
    for entry in translations:
        # ``example.yaml`` documents the workflow; it is not part of the delivered set
        if entry.file_path.endswith("example.yaml"):
            continue
        if entry.reviewed:
            # reviewed translations go to dtc_definitions via the normal loader, not here
            continue
        row = conn.execute(
            "SELECT id FROM dtc_codes WHERE context_key = ?", (entry.context_key,)
        ).fetchone()
        if row is None:
            warnings.append(
                f"translation draft for {entry.code} ({entry.context_key}) has no matching code"
            )
            continue
        key = (entry.context_key, entry.language)
        if key in seen:
            warnings.append(f"duplicate translation draft for {entry.context_key} ignored")
            continue
        seen.add(key)
        conn.execute(
            """
            INSERT INTO translation_drafts (dtc_code_id, language, title, description,
                context_ar, reviewed, translator, reviewer, source_url, file_path, created_at)
            VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, datetime('now'))
            """,
            (
                row[0],
                entry.language,
                entry.title,
                entry.description,
                getattr(entry, "context_ar", None),
                entry.translator,
                entry.reviewer,
                entry.source_url,
                entry.file_path,
            ),
        )
        inserted += 1
    conn.commit()
    return inserted


def _populate_priority(conn: sqlite3.Connection) -> int:
    conn.execute("DELETE FROM dtc_priority")
    index = priority_index(conn)
    conn.executemany(
        """
        INSERT INTO dtc_priority (dtc_code_id, tier, score, reasons_json, open_conflicts,
            critical_conflicts, contexts, source_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                entry["dtc_code_id"],
                entry["tier"],
                entry["score"],
                json.dumps(entry["reasons"], ensure_ascii=False),
                entry["open_conflicts"],
                entry["critical_conflicts"],
                entry["contexts"],
                entry["sources"],
            )
            for entry in index
        ],
    )
    conn.commit()
    return len(index)


def _verify(conn: sqlite3.Connection) -> None:
    """Fail the build rather than ship a table that contradicts its own labels."""
    problems: list[str] = []
    unclassified = conn.execute(
        "SELECT COUNT(*) FROM source_quotes WHERE category IS NULL OR category = ''"
    ).fetchone()[0]
    if unclassified:
        problems.append(f"{unclassified} quote(s) without a category")
    approved = conn.execute(
        "SELECT COUNT(*) FROM procedure_scope WHERE approval_status <> 'not_approved'"
    ).fetchone()[0]
    if approved:
        problems.append(f"{approved} scope row(s) claim an approved procedure")
    reviewed = conn.execute(
        "SELECT COUNT(*) FROM translation_drafts WHERE reviewed <> 0"
    ).fetchone()[0]
    if reviewed:
        problems.append(f"{reviewed} draft(s) claim to be reviewed")
    orphan_scope = conn.execute(
        "SELECT COUNT(*) FROM procedure_scope p "
        "WHERE NOT EXISTS (SELECT 1 FROM source_quotes q WHERE q.dtc_code_id = p.dtc_code_id)"
    ).fetchone()[0]
    if orphan_scope:
        problems.append(f"{orphan_scope} scope row(s) without quotes")
    missing_priority = conn.execute(
        "SELECT COUNT(*) FROM dtc_codes c "
        "WHERE NOT EXISTS (SELECT 1 FROM dtc_priority p WHERE p.dtc_code_id = c.id)"
    ).fetchone()[0]
    if missing_priority:
        problems.append(f"{missing_priority} code(s) without a priority row")
    if problems:
        raise AppContentError("; ".join(problems))
