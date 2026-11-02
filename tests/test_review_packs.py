"""Priority ranking and review packs: order is deterministic, drafts stay drafts."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import yaml

from autodoctor_data_engine.reporting.priority import priority_index, summarise
from autodoctor_data_engine.reporting.review_pack import build_pack, load_arabic


def _index(built):
    conn = sqlite3.connect(f"file:{built.database_path}?mode=ro", uri=True)
    try:
        return priority_index(conn)
    finally:
        conn.close()


def test_ranking_is_deterministic_and_ordered(built) -> None:
    first = _index(built)
    second = _index(built)
    assert [e["dtc_code_id"] for e in first] == [e["dtc_code_id"] for e in second]
    keys = [(e["tier"], -e["score"]) for e in first]
    assert keys == sorted(keys), "tiers first, then score descending"
    assert {e["tier"] for e in first} <= {1, 2, 3, 4}


def test_tier_one_has_a_stated_safety_reason(built) -> None:
    for entry in _index(built):
        if entry["tier"] == 1:
            text = " ".join(entry["reasons"])
            assert "safety component" in text or (
                "risk_level=high" in text and "limp mode" in text
            ), entry["context_key"]


def test_day_summary_counts_every_identity(built) -> None:
    index = _index(built)
    summary = summarise(index)
    assert summary["identities"] == len(index)
    assert sum(t["identities"] for t in summary["by_tier"].values()) == len(index)


def test_pack_never_promotes_a_draft_or_invents_a_procedure(built, tmp_path: Path) -> None:
    arabic_path = tmp_path / "ar.yaml"
    arabic_path.write_text(
        yaml.safe_dump(
            [
                {
                    "code": "P0301",
                    "title": "مسودة",
                    "description": "مسودة",
                    "translator": "",
                    "reviewer": "",
                    "reviewed": False,
                }
            ],
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    conn = sqlite3.connect(f"file:{built.database_path}?mode=ro", uri=True)
    try:
        index = priority_index(conn)
        pack = build_pack(conn, index, load_arabic(arabic_path), tier=1, limit=5)
    finally:
        conn.close()

    assert pack["entries"], "the fixture must have tier 1 entries"
    for entry in pack["entries"]:
        procedure = entry["procedure"]
        assert procedure["tools"] == [], "no tool list may be generated"
        assert procedure["nominal_values"] == [], "no measurement value may be generated"
        assert entry["arabic_draft"]["status"] in {"machine_draft", "not_authored"}
        if procedure["status"] == "draft_unreviewed":
            assert procedure["quoted_checks"], "a draft needs quoted source text"
            assert all(step["source"] for step in procedure["quoted_checks"])
    assert "not approved" in pack["warning"].lower() or "only" in pack["warning"].lower()
