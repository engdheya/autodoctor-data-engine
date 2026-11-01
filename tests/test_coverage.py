"""Coverage must be measured against the population we claim, never against survivors."""

from __future__ import annotations

import json
from pathlib import Path

from autodoctor_data_engine.reporting.coverage import (
    SCOPE,
    coverage_report,
    render_coverage_markdown,
    write_coverage,
)


def test_coverage_counts_match_the_database(built, db_conn) -> None:
    report = coverage_report(db_conn)
    total = db_conn.execute("SELECT COUNT(*) FROM dtc_codes").fetchone()[0]
    assert report["dtc"]["identities"] == total
    assert report["dtc"]["distinct_codes"] <= total
    assert sum(report["dtc"]["by_context"].values()) == total
    assert sum(report["dtc"]["by_family"].values()) == total
    assert report["dtc"]["manufacturer_contexts"] == report["dtc"]["by_context"].get(
        "manufacturer", 0
    )


def test_every_ratio_publishes_its_denominator(built, db_conn) -> None:
    report = coverage_report(db_conn)
    total = report["dtc"]["identities"]
    for row in report["content"]["coverage"]:
        assert row["denominator"] == total, row
        assert row["count"] <= total, row
        if total:
            assert 0.0 <= row["percent"] <= 100.0
    # a field can never be claimed for more identities than exist
    assert report["content"]["diagnosis_ready"] == report["content"]["with_causes"]


def test_markdown_states_scope_and_every_gap_block(built, db_conn) -> None:
    report = coverage_report(db_conn)
    text = render_coverage_markdown(report)
    assert "Declared scope" in text
    for unsupported in SCOPE["not_declared"]:
        assert unsupported in text
    assert "Denominator:" in text

    # the procedure block always renders its measured count, and the "no content"
    # warning is tied to that count rather than to a hardcoded assumption
    procedures = report["procedures"]["procedures"]
    assert f"procedures: **{procedures:,}**" in text
    assert ("Zero procedures" in text) is (procedures == 0)

    # same for the vehicle block
    vehicles = report["vehicles"]
    empty = not vehicles["vehicles"] and not vehicles["ecus"]
    assert ("Vehicle-based search is therefore **not supported**" in text) is empty


def test_write_coverage_emits_json_and_markdown(built, db_conn, tmp_path: Path) -> None:
    json_path, md_path = write_coverage(db_conn, tmp_path / "reports")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["declared_support"]["dtc_identities"] == payload["dtc"]["identities"]
    assert "# Data coverage report" in md_path.read_text(encoding="utf-8")
