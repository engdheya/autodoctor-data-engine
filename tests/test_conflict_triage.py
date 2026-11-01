"""Triage orders the review queue; it must never decide anything."""

from __future__ import annotations

from pathlib import Path

from autodoctor_data_engine.conflict_resolution.triage import (
    BANDS,
    CRITICAL_SIMILARITY,
    VARIANT_SIMILARITY,
    render_triage_markdown,
    triage_conflicts,
    write_triage,
)


def test_every_conflict_gets_exactly_one_band(built, db_conn) -> None:
    report = triage_conflicts(db_conn)
    total = db_conn.execute("SELECT COUNT(*) FROM conflicts").fetchone()[0]
    assert report["totals"]["conflicts"] == total
    assert sum(report["totals"]["by_band"].values()) == total
    assert set(report["totals"]["by_band"]) == set(BANDS)
    assert len(report["items"]) == total
    assert all(item["band"] in BANDS for item in report["items"])
    assert all(item["reason"] for item in report["items"])


def test_bands_follow_the_documented_rules(built, db_conn) -> None:
    report = triage_conflicts(db_conn)
    for item in report["items"]:
        similarity = item["similarity"] or 0.0
        if item["context_type"] == "generic":
            if item["risk_level"] in ("high", "critical") and similarity < CRITICAL_SIMILARITY:
                assert item["band"] == "critical", item
            else:
                assert item["band"] == "high", item
        elif similarity >= VARIANT_SIMILARITY:
            assert item["band"] == "low", item
        else:
            assert item["band"] == "medium", item


def test_triage_never_writes_a_decision(built, db_conn) -> None:
    before = db_conn.execute(
        "SELECT status, resolution_note FROM conflicts ORDER BY id"
    ).fetchall()
    triage_conflicts(db_conn)
    after = db_conn.execute(
        "SELECT status, resolution_note FROM conflicts ORDER BY id"
    ).fetchall()
    assert before == after
    assert all(row[0] == "needs_review" for row in after)


def test_report_and_files_carry_the_queue(built, db_conn, tmp_path: Path) -> None:
    text = render_triage_markdown(triage_conflicts(db_conn))
    assert "Triage is an **order of work**, not a decision" in text
    for band in BANDS:
        if triage_conflicts(db_conn)["totals"]["by_band"][band]:
            assert f"## {band} batch" in text
    json_path, md_path = write_triage(db_conn, tmp_path / "reports")
    assert json_path.is_file() and md_path.is_file()
