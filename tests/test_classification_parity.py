"""One classifier, two consumers: the tier export and the per-code packs must agree.

The regression this file guards: the packs used to select sentences with the old
``CHECK_WORDS`` heuristic, so a sentence such as "Ford checks plausibility of the pedal
signal" was listed under ``quoted_checks`` as if a technician could perform it.

The comparison is keyed on ``context_key`` - a code alone is not an identity, because P0501
for one manufacturer and P0501 generic are different rows - and it checks the expected list
in full, including the five-quote display cap, instead of only asserting a subset.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from autodoctor_data_engine.reporting.priority import priority_index
from autodoctor_data_engine.reporting.procedures import build_entries, classify_sentences
from autodoctor_data_engine.reporting.quote_classify import CATEGORIES
from autodoctor_data_engine.reporting.review_pack import (
    MAX_QUOTED_CHECKS,
    _procedure,
    build_pack,
)

MONITORING = (
    "Ford checks plausibility of the pedal signal against the second track at every start, "
    "and a mismatch that persists for two driving cycles stores the code."
)
CHECK = "Check the connector pins for corrosion with a multimeter before replacing the sensor."
MANY_CHECKS = " ".join(
    [
        "Check the supply voltage at pin 1 with a multimeter.",
        "Measure the resistance between pin 2 and ground.",
        "Inspect the connector for corrosion and pushed-back pins.",
        "Swap the sensor with a known-good part and recheck the value.",
        "Probe the signal wire with an oscilloscope while wiggling the harness.",
        "Verify continuity of the ground wire back to the body.",
    ]
)


def _conn(built):
    return sqlite3.connect(f"file:{built.database_path}?mode=ro", uri=True)


def compare_quotes(export_entry: dict[str, Any], procedure: dict[str, Any]) -> list[str]:
    """Problems between one exported code and its pack counterpart (empty means equal).

    ``export_entry`` is an entry of ``procedures.build_entries`` for the same context; the
    pack shows at most ``MAX_QUOTED_CHECKS`` diagnostic sentences but must report the real
    total in ``diagnostic_quotes_total``.
    """
    problems: list[str] = []
    key = export_entry["context_key"]

    expected_checks = [
        quote["text_en"]
        for quote in export_entry["quotes"]
        if quote["category"] == "diagnostic_check"
    ]
    shown = [quote["text_en"] for quote in procedure["quoted_checks"]]
    if shown != expected_checks[:MAX_QUOTED_CHECKS]:
        problems.append(
            f"{key}: diagnostic checks differ "
            f"(pack {len(shown)} of {len(expected_checks)} expected, capped at {MAX_QUOTED_CHECKS})"
        )
    if procedure["diagnostic_quotes_total"] != len(expected_checks):
        problems.append(
            f"{key}: total diagnostic quotes {procedure['diagnostic_quotes_total']} "
            f"!= export {len(expected_checks)}"
        )
    if procedure["quotes_truncated"] != (len(expected_checks) > MAX_QUOTED_CHECKS):
        problems.append(f"{key}: truncation flag is wrong")

    expected_others = {
        quote["text_en"]: quote["category"]
        for quote in export_entry["quotes"]
        if quote["category"] != "diagnostic_check"
    }
    shown_others = {quote["text_en"]: quote["category"] for quote in procedure["other_quotes"]}
    if shown_others != expected_others:
        missing = set(expected_others) - set(shown_others)
        extra = set(shown_others) - set(expected_others)
        reclassified = {
            text
            for text in set(expected_others) & set(shown_others)
            if expected_others[text] != shown_others[text]
        }
        problems.append(
            f"{key}: other quotes differ (missing {len(missing)}, extra {len(extra)}, "
            f"reclassified {len(reclassified)})"
        )

    for quote in procedure["quoted_checks"]:
        if quote["category"] != "diagnostic_check":
            problems.append(f"{key}: non-diagnostic quote inside quoted_checks")
    return problems


def test_parity_between_pack_and_export_by_context_key(built) -> None:
    conn = _conn(built)
    try:
        index = priority_index(conn)
        export = build_entries(conn, index, (1,))
        pack = build_pack(conn, index, {}, tier=1, limit=1000)
    finally:
        conn.close()

    exported = {entry["context_key"]: entry for entry in export["entries"]}
    compared = 0
    problems: list[str] = []
    for entry in pack["entries"]:
        export_entry = exported.get(entry["context_key"])
        if export_entry is None:
            problems.append(f"{entry['context_key']}: in the pack but missing from the export")
            continue
        if export_entry["code"] != entry["code"]:
            problems.append(f"{entry['context_key']}: code mismatch")
        problems.extend(compare_quotes(export_entry, entry["procedure"]))
        compared += 1

    assert not problems, "\n".join(problems[:10])
    assert compared >= 1, "the fixture must contain a tier 1 context present in both outputs"


def test_comparator_catches_a_lost_diagnostic_quote(built) -> None:
    """If a real check disappears from the pack, the comparison must fail - not pass quietly."""
    description = CHECK + " " + MONITORING
    quotes = classify_sentences(description)
    export_entry = {"context_key": "synthetic|generic:generic", "quotes": quotes}

    conn = _conn(built)
    try:
        procedure = _procedure(conn, 1, description)
    finally:
        conn.close()

    assert [q["text_en"] for q in procedure["quoted_checks"]] == [CHECK]
    assert compare_quotes(export_entry, procedure) == [], "the untouched procedure must match"

    broken = dict(procedure)
    broken["quoted_checks"] = []
    problems = compare_quotes(export_entry, broken)
    assert problems, "dropping a diagnostic quote must be reported"
    assert any("diagnostic checks differ" in problem for problem in problems)

    reclassified = dict(procedure)
    reclassified["other_quotes"] = [
        {"text_en": quote["text_en"], "category": "non_procedure"}
        for quote in procedure["other_quotes"]
    ]
    assert any("other quotes differ" in p for p in compare_quotes(export_entry, reclassified))


def test_display_cap_is_reported(built) -> None:
    conn = _conn(built)
    try:
        procedure = _procedure(conn, 1, MANY_CHECKS)
    finally:
        conn.close()

    assert len(procedure["quoted_checks"]) == MAX_QUOTED_CHECKS
    assert procedure["diagnostic_quotes_total"] == 6
    assert procedure["quotes_truncated"] is True


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


def test_classification_helper_is_shared() -> None:
    quotes = classify_sentences(MONITORING + " " + CHECK)
    categories = {quote["text_en"]: quote["category"] for quote in quotes}
    assert categories[MONITORING] == "monitoring_description"
    assert categories[CHECK] == "diagnostic_check"
