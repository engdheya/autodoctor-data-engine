"""One classifier, two consumers: the tier export and the per-code packs must agree.

The regression this file guards: the packs used to select sentences with the old
``CHECK_WORDS`` heuristic, so a sentence such as "Ford checks plausibility of the pedal
signal" was listed under ``quoted_checks`` as if a technician could perform it.
"""

from __future__ import annotations

import sqlite3

from autodoctor_data_engine.reporting.priority import priority_index
from autodoctor_data_engine.reporting.procedures import build_entries, classify_sentences
from autodoctor_data_engine.reporting.quote_classify import CATEGORIES
from autodoctor_data_engine.reporting.review_pack import _procedure, build_pack

MONITORING = (
    "Ford checks plausibility of the pedal signal against the second track at every start, "
    "and a mismatch that persists for two driving cycles stores the code."
)
CHECK = "Check the connector pins for corrosion with a multimeter before replacing the sensor."


def _conn(built):
    return sqlite3.connect(f"file:{built.database_path}?mode=ro", uri=True)


def test_monitoring_sentence_is_not_a_quoted_check(built) -> None:
    conn = _conn(built)
    try:
        procedure = _procedure(conn, 1, MONITORING)
    finally:
        conn.close()

    assert procedure["quoted_checks"] == [], "a monitoring sentence must never be a procedure"
    assert "monitoring_description" in procedure["quote_categories"]
    texts = [q["text_en"] for q in procedure["other_quotes"]]
    assert any("Ford checks plausibility" in text for text in texts)
    assert all(q["category"] != "diagnostic_check" for q in procedure["other_quotes"])
    assert procedure["status"] != "draft_unreviewed"


def test_real_check_sentence_is_a_quoted_check(built) -> None:
    conn = _conn(built)
    try:
        procedure = _procedure(conn, 1, CHECK)
    finally:
        conn.close()

    assert [q["text_en"] for q in procedure["quoted_checks"]] == [CHECK]
    assert procedure["quoted_checks"][0]["category"] == "diagnostic_check"
    assert procedure["status"] == "draft_unreviewed"


def test_every_quote_carries_a_category(built) -> None:
    conn = _conn(built)
    try:
        pack = build_pack(conn, priority_index(conn), {}, tier=1, limit=10)
    finally:
        conn.close()

    for entry in pack["entries"]:
        for quote in entry["procedure"]["quoted_checks"]:
            assert quote["category"] == "diagnostic_check"
            assert quote["category"] in CATEGORIES
            assert quote["classification"]["rule"]


def test_pack_matches_the_tier_export_for_the_same_codes(built) -> None:
    """Integration: the same code must classify identically in both outputs."""
    conn = _conn(built)
    try:
        index = priority_index(conn)
        export = build_entries(conn, index, (1,))
        pack = build_pack(conn, index, {}, tier=1, limit=1000)

        exported = {entry["code"]: entry for entry in export["entries"]}
        checked = 0
        for entry in pack["entries"]:
            if entry["code"] not in exported:
                continue
            expected = {
                quote["text_en"]
                for quote in exported[entry["code"]]["quotes"]
                if quote["category"] == "diagnostic_check"
            }
            got = {quote["text_en"] for quote in entry["procedure"]["quoted_checks"]}
            assert got <= expected, f"{entry['code']}: pack found a check the export did not"
            if expected:
                assert got, f"{entry['code']}: export has a check the pack dropped"
            checked += 1
    finally:
        conn.close()
    assert checked >= 1, "the fixture must contain a tier 1 code present in both outputs"


def test_classification_helper_is_shared() -> None:
    quotes = classify_sentences(MONITORING + " " + CHECK)
    categories = {quote["text_en"]: quote["category"] for quote in quotes}
    assert categories[MONITORING] == "monitoring_description"
    assert categories[CHECK] == "diagnostic_check"
