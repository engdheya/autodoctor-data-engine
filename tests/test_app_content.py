"""The client content tables must say exactly what the database already said.

``source_quotes`` may only contain verbatim sentences, ``procedure_scope`` may never claim an
approval, ``translation_drafts`` may never claim a review, and ``dtc_priority`` must equal the
ranking the review exports publish. These are the guarantees the Flutter client relies on, so
they are tested against the built artifact rather than assumed.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import yaml

from autodoctor_data_engine.reporting.priority import priority_index

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_BUNDLE = REPO_ROOT / "data" / "exports" / "autodoctor-app-0.9.1-public.sqlite"
REAL_EXPORT = REPO_ROOT / "data" / "reviews" / "procedures" / "procedures-quoted.yaml"


def _ro(path: Path | str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _drafts_in_files() -> dict[str, dict]:
    drafts: dict[str, dict] = {}
    for path in sorted((REPO_ROOT / "data" / "translations").glob("*/*.yaml")):
        if path.name == "example.yaml":
            continue
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        if not isinstance(payload, list):  # glossary.yaml is a term list, not drafts
            continue
        for entry in payload:
            drafts.setdefault(entry["code"], entry)
    return drafts


def test_quotes_are_verbatim_substrings(built) -> None:
    conn = _ro(built.database_path)
    try:
        rows = conn.execute(
            """
            SELECT q.text_en, d.description
            FROM source_quotes q
            JOIN dtc_definitions d
              ON d.dtc_code_id = q.dtc_code_id AND d.language = 'en' AND d.is_canonical = 1
            """
        ).fetchall()
    finally:
        conn.close()

    assert rows, "the fixture must produce at least one quote"
    paraphrased = [text for text, description in rows if text not in (description or "")]
    assert not paraphrased, f"{len(paraphrased)} quote(s) are not verbatim"


def test_every_quote_has_a_category_and_a_rule(built) -> None:
    conn = _ro(built.database_path)
    try:
        bad = conn.execute(
            "SELECT COUNT(*) FROM source_quotes "
            "WHERE category = '' OR classification_rule = '' OR quote_status = ''"
        ).fetchone()[0]
    finally:
        conn.close()
    assert bad == 0


def test_scope_never_claims_approval(built) -> None:
    conn = _ro(built.database_path)
    try:
        approved = conn.execute(
            "SELECT COUNT(*) FROM procedure_scope WHERE approval_status <> 'not_approved'"
        ).fetchone()[0]
        verified = conn.execute(
            "SELECT COUNT(*) FROM procedure_scope WHERE applicability <> 'unverified'"
        ).fetchone()[0]
        orphans = conn.execute(
            "SELECT COUNT(*) FROM procedure_scope p WHERE NOT EXISTS "
            "(SELECT 1 FROM source_quotes q WHERE q.dtc_code_id = p.dtc_code_id)"
        ).fetchone()[0]
    finally:
        conn.close()
    assert (approved, verified, orphans) == (0, 0, 0)


def test_drafts_are_stored_unreviewed(built) -> None:
    conn = _ro(built.database_path)
    try:
        reviewed = conn.execute(
            "SELECT COUNT(*) FROM translation_drafts WHERE reviewed <> 0"
        ).fetchone()[0]
        stored = conn.execute("SELECT COUNT(*) FROM translation_drafts").fetchone()[0]
    finally:
        conn.close()
    assert reviewed == 0
    assert stored >= 1, "the fixture ships an unreviewed Arabic draft"


def test_priority_covers_every_code_and_matches_the_rule(built) -> None:
    conn = _ro(built.database_path)
    try:
        missing = conn.execute(
            "SELECT COUNT(*) FROM dtc_codes c WHERE NOT EXISTS "
            "(SELECT 1 FROM dtc_priority p WHERE p.dtc_code_id = c.id)"
        ).fetchone()[0]
        bad_tier = conn.execute(
            "SELECT COUNT(*) FROM dtc_priority WHERE tier NOT BETWEEN 1 AND 4"
        ).fetchone()[0]
        stored = {
            row[0]: (row[1], row[2], row[3], row[4])
            for row in conn.execute(
                "SELECT dtc_code_id, tier, score, open_conflicts, critical_conflicts "
                "FROM dtc_priority"
            )
        }
        computed = {
            entry["dtc_code_id"]: (
                entry["tier"],
                entry["score"],
                entry["open_conflicts"],
                entry["critical_conflicts"],
            )
            for entry in priority_index(conn)
        }
    finally:
        conn.close()

    assert missing == 0
    assert bad_tier == 0
    assert stored == computed


def test_app_bundle_exposes_the_client_views(built) -> None:
    bundle = Path(built.app_bundle_path)
    assert bundle.is_file(), "build_database must produce an app bundle"
    conn = _ro(bundle)
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        views = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'view'")
        }
        for name in ("source_quotes", "procedure_scope", "translation_drafts", "dtc_priority"):
            assert name in tables, name
        for name in ("v_dtc_source_quotes", "v_dtc_priority", "v_translation_drafts"):
            assert name in views, name
        assert conn.execute("SELECT COUNT(*) FROM v_dtc_priority").fetchone()[0] > 0
        approval = {
            row[0] for row in conn.execute("SELECT DISTINCT approval_status FROM v_dtc_source_quotes")
        }
        assert approval <= {"not_approved"}
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


@pytest.mark.skipif(not REAL_BUNDLE.is_file(), reason="0.9.1 app bundle is not built here")
def test_real_bundle_quotes_match_the_audit_export() -> None:
    """Per ``context_key``: same sentences, same categories, no paraphrase, nothing dropped."""
    export = yaml.safe_load(REAL_EXPORT.read_text(encoding="utf-8"))
    conn = _ro(REAL_BUNDLE)
    try:
        rows = conn.execute(
            """
            SELECT c.context_key, q.text_en, q.category
            FROM source_quotes q JOIN dtc_codes c ON c.id = q.dtc_code_id
            ORDER BY c.context_key, q.ordinal
            """
        ).fetchall()
    finally:
        conn.close()

    stored: dict[str, list[tuple[str, str]]] = {}
    for key, text, category in rows:
        stored.setdefault(key, []).append((text, category))

    problems: list[str] = []
    for entry in export["entries"]:
        key = entry["context_key"]
        expected = [(q["text_en"], q["category"]) for q in entry["quotes"]]
        if stored.get(key) != expected:
            problems.append(f"{key}: {len(stored.get(key, []))} stored vs {len(expected)} expected")
    assert not problems, "\n".join(problems[:10])


@pytest.mark.skipif(not REAL_BUNDLE.is_file(), reason="0.9.1 app bundle is not built here")
def test_real_bundle_drafts_are_the_delivered_drafts() -> None:
    expected = _drafts_in_files()
    conn = _ro(REAL_BUNDLE)
    try:
        stored = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT c.code, t.title FROM translation_drafts t "
                "JOIN dtc_codes c ON c.id = t.dtc_code_id"
            )
        }
        reviewed = conn.execute(
            "SELECT COUNT(*) FROM translation_drafts WHERE reviewed <> 0"
        ).fetchone()[0]
    finally:
        conn.close()

    assert reviewed == 0
    assert set(stored) == set(expected), "every delivered draft must be present, with no extras"
    assert len(stored) == 100
