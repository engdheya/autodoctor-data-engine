"""Translations are human-supplied only, and reviewed ones are gated."""

from __future__ import annotations

import csv
from pathlib import Path

from autodoctor_data_engine.database.connection import connect
from autodoctor_data_engine.translations import export_template, load_translations


def test_only_reviewed_translations_are_loaded(settings) -> None:
    entries, warnings = load_translations(settings)
    assert len(entries) == 1
    assert entries[0].code == "P0301"
    assert entries[0].reviewed is True
    assert entries[0].reviewer
    # the unreviewed P0420 entry is reported, not silently dropped
    assert any("not reviewed" in warning for warning in warnings)


def test_unreviewed_can_be_included_explicitly(settings) -> None:
    entries, _ = load_translations(settings, include_unreviewed=True)
    assert {entry.code for entry in entries} == {"P0301", "P0420"}


def test_database_contains_the_reviewed_arabic_definition(built, db_conn) -> None:
    row = db_conn.execute(
        """
        SELECT d.title, d.is_translated, d.translation_reviewed, d.is_canonical
        FROM dtc_codes c JOIN dtc_definitions d ON d.dtc_code_id = c.id
        WHERE c.code = 'P0301' AND d.language = 'ar'
        """
    ).fetchone()
    assert row is not None
    assert row["title"].startswith("تم اكتشاف")
    assert row["is_translated"] == 1
    assert row["translation_reviewed"] == 1
    assert row["is_canonical"] == 1

    translation = db_conn.execute("SELECT * FROM translations").fetchone()
    assert translation["translator"] and translation["reviewer"]


def test_unreviewed_translation_is_absent(built, db_conn) -> None:
    rows = db_conn.execute(
        """
        SELECT COUNT(*) FROM dtc_codes c JOIN dtc_definitions d ON d.dtc_code_id = c.id
        WHERE c.code = 'P0420' AND d.language = 'ar'
        """
    ).fetchone()[0]
    assert rows == 0
    assert built.counts["codes_with_arabic"] == 1


def test_translation_claim_is_marked_translated(db_conn) -> None:
    claim = db_conn.execute(
        """
        SELECT p.is_translated, p.verification_status, s.slug FROM provenance_claims p
        JOIN data_sources s ON s.id = p.source_id
        WHERE p.entity_type = 'dtc_definition' AND p.is_translated = 1
        """
    ).fetchone()
    assert claim is not None
    assert claim["slug"] == "local-translations"
    assert claim["verification_status"] == "verified"


def test_translation_template_lists_missing_codes(built, tmp_path: Path) -> None:
    conn = connect(built.database_path, readonly=True)
    try:
        target = tmp_path / "template.csv"
        count = export_template(conn, target, language="ar")
    finally:
        conn.close()
    assert count >= 1
    with open(target, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows and rows[0]["code"] != "P0301"  # already translated
    assert rows[0]["title_ar"] == ""
