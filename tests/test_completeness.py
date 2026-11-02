"""Per-code completeness must count, not fill."""

from __future__ import annotations

from pathlib import Path

from autodoctor_data_engine.reporting.completeness import (
    FIELDS,
    completeness_report,
    render_completeness,
    write_completeness,
)


def test_every_identity_is_reported_with_its_gaps(built, db_conn) -> None:
    report = completeness_report(db_conn)
    total = db_conn.execute("SELECT COUNT(*) FROM dtc_codes").fetchone()[0]
    assert report["totals"]["identities"] == total
    assert len(report["items"]) == total
    for item in report["items"]:
        assert set(item["present"]) | set(item["missing"]) == set(FIELDS)
        assert not set(item["present"]) & set(item["missing"])
    # the tier is defined by causes, not by having a title
    for item in report["items"]:
        assert (item["tier"] == "diagnosis_ready") is ("causes" in item["present"])


def test_work_lists_name_the_codes_not_just_the_count(built, db_conn) -> None:
    report = completeness_report(db_conn)
    worklists = report["worklists"]
    assert isinstance(worklists["missing_causes"], list)
    definition_only = report["totals"]["definition_only"]
    assert len(worklists["missing_causes"]) == definition_only
    text = render_completeness(report)
    assert "codes with no causes" in text
    assert f"({definition_only:,})" in text


def test_files_are_written_for_the_reviewer(built, db_conn, tmp_path: Path) -> None:
    json_path, md_path, csv_path = write_completeness(db_conn, tmp_path / "reports")
    header = csv_path.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert header[:5] == ["code", "context_type", "context_key", "manufacturer", "tier"]
    assert header[5:] == ["field_count", *FIELDS]
    assert len(csv_path.read_text(encoding="utf-8").splitlines()) > 1
    assert md_path.is_file() and json_path.is_file()
