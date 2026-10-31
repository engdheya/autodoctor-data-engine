"""The committed sample database must stay reproducible and honest."""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path
from types import ModuleType

import pytest
from helpers import REPO_ROOT

from autodoctor_data_engine.database.app_export import LicenceError
from autodoctor_data_engine.database.build import build_database


def _sample_module() -> ModuleType:
    path = REPO_ROOT / "scripts" / "build_sample_db.py"
    spec = importlib.util.spec_from_file_location("build_sample_db", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sample_preserves_content_and_provenance(imported, tmp_path: Path) -> None:
    module = _sample_module()
    built = build_database(
        imported, version="9.0.0", app_bundle=True, source_set="public"
    )
    assert built.app_bundle_path is not None
    target = tmp_path / "sample.sqlite"
    counts = module.build_sample(built.app_bundle_path, target, limit=5, codes=["P0301"])

    assert counts["dtc_codes"] >= 1
    assert counts["provenance_summary"] > 0
    assert counts["dtc_definitions"] >= 1
    assert target.stat().st_size > 20_000

    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM v_dtc_summary WHERE code = 'P0301'").fetchone()
        assert row is not None
        assert row["title_en"]
        assert row["cause_count"] >= 1

        # the compact provenance travels with the sample
        assert conn.execute(
            "SELECT COUNT(*) FROM provenance_summary WHERE entity_type = 'dtc_code'"
        ).fetchone()[0] >= 1

        # the views are recreated, so the sample answers the same queries
        assert conn.execute("SELECT COUNT(*) FROM v_dtc_lookup").fetchone()[0] >= 1

        # and it never carries a source that may not be redistributed
        assert all(
            row["legal_review_status"] == "approved"
            for row in conn.execute("SELECT legal_review_status FROM data_sources")
        )
    finally:
        conn.close()


def test_sample_refuses_a_private_database(built, tmp_path: Path) -> None:
    """A sample is published, so it follows the public licence rule."""
    module = _sample_module()
    assert built.app_bundle_path is not None
    with pytest.raises(LicenceError, match="refusing to sample"):
        module.build_sample(built.app_bundle_path, tmp_path / "out.sqlite", limit=5, codes=[])
    assert not (tmp_path / "out.sqlite").exists()


def test_sample_script_rejects_a_missing_bundle(tmp_path: Path) -> None:
    module = _sample_module()
    try:
        module.build_sample(tmp_path / "nope.sqlite", tmp_path / "out.sqlite", limit=1, codes=[])
    except SystemExit as exc:
        assert "not found" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a missing bundle must not silently produce a sample")


def test_sampling_never_modifies_the_published_bundle(imported, tmp_path: Path) -> None:
    """Generating a sample must not touch the release artifact it reads.

    An unqualified ``DROP VIEW``/``CREATE VIEW`` while the bundle was attached
    once stripped a published bundle of its views; the source is now attached
    read-only and the file is compared byte for byte.
    """
    module = _sample_module()
    built = build_database(
        imported, version="9.0.1", app_bundle=True, source_set="public"
    )
    assert built.app_bundle_path is not None
    before = built.app_bundle_path.read_bytes()
    module.build_sample(built.app_bundle_path, tmp_path / "sample.sqlite", limit=5, codes=[])
    assert built.app_bundle_path.read_bytes() == before
