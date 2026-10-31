"""Change detection between two releases."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from helpers import create_project

from autodoctor_data_engine.config import Settings
from autodoctor_data_engine.database.build import build_database
from autodoctor_data_engine.pipeline import import_source
from autodoctor_data_engine.reporting.changes import detect_changes, render_changes


@pytest.fixture(scope="module")
def two_releases(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    root = create_project(tmp_path_factory.mktemp("autodoctor-changes"))
    settings = Settings(root=root)
    for slug in ("obdex", "wal33d", "autodiag"):
        import_source(settings, slug)
    first = build_database(settings, version="0.1.0", app_bundle=False)
    assert first.test_status == "passed"

    # upstream drops a Wal33D row (the only source for P1741)
    db = settings.sources["wal33d"].local_path / "data" / "dtc_codes.db"
    conn = sqlite3.connect(db)
    with conn:
        conn.execute("DELETE FROM dtc_definitions WHERE code = 'P1741'")
        conn.execute(
            "INSERT INTO dtc_definitions (code, manufacturer, description, type, locale, "
            "is_generic, source_file) VALUES ('P0500', 'GENERIC', "
            "'Vehicle Speed Sensor A Malfunction', 'P', 'en', 1, 'p_codes')"
        )
    conn.close()

    import_source(settings, "wal33d")
    second = build_database(settings, version="0.2.0", app_bundle=False)
    assert second.test_status == "passed"
    return first.export_path, second.database_path


def test_changes_are_detected(two_releases) -> None:
    previous, current = two_releases
    report = detect_changes(previous, current)
    assert report["records"]["added"] >= 1
    assert report["records"]["removed"] >= 1
    assert any("P1741" in sample for sample in report["records"]["samples"]["removed"])
    assert any("P0500" in sample for sample in report["records"]["samples"]["added"])
    assert report["codes"]["removed"] >= 1


def test_vanished_records_are_reported_not_deleted(two_releases) -> None:
    previous, current = two_releases
    report = detect_changes(previous, current)
    # the report says so explicitly, and the code list is informational only
    assert "retained" in report["codes"]["note"]
    assert report["records"]["removed"] >= 1


def test_change_report_renders(two_releases) -> None:
    previous, current = two_releases
    text = render_changes(detect_changes(previous, current))
    assert "# Change report" in text
    assert "Records" in text
    assert "DTC identities" in text
