"""The licence boundary: a public build must not contain unapproved data.

These tests exercise the separation end to end - config, build filtering, the
release gates and the bundle guard - because documentation alone is not a
control.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from helpers import create_project

from autodoctor_data_engine.config import ConfigError, Settings
from autodoctor_data_engine.database.app_export import (
    LicenceError,
    assert_public_safe,
    build_app_bundle,
    unlicensed_sources,
)
from autodoctor_data_engine.database.build import build_database
from autodoctor_data_engine.database.connection import connect
from autodoctor_data_engine.pipeline import import_source
from autodoctor_data_engine.validators.database_rules import failed_blocking, run_database_checks

APPROVED = {"obdex", "wal33d"}
LOCAL = {"local-translations"}   # project-owned translations, always licensed
PENDING = {"autodiag", "obdb"}


@pytest.fixture(scope="module")
def staged_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = create_project(tmp_path_factory.mktemp("autodoctor-licence"))
    settings = Settings(root=root)
    for slug in ("obdex", "wal33d", "autodiag", "obdb"):
        import_source(settings, slug)
    return root


def _claim_sources(db_path: Path) -> dict[str, int]:
    conn = connect(db_path, readonly=True)
    try:
        rows = conn.execute(
            """
            SELECT s.slug, COUNT(*) FROM provenance_claims p
            JOIN data_sources s ON s.id = p.source_id
            GROUP BY s.slug
            """
        ).fetchall()
    finally:
        conn.close()
    return {row[0]: int(row[1]) for row in rows}


# ---------------------------------------------------------------------------
# configuration level
# ---------------------------------------------------------------------------

def test_source_sets_are_derived_from_the_licence_record(staged_project: Path) -> None:
    settings = Settings(root=staged_project)
    assert set(settings.source_set_slugs("private")) == APPROVED | PENDING
    assert set(settings.source_set_slugs("public")) == APPROVED

    report = settings.source_set_report("public")
    excluded = {entry["slug"]: entry["reason"] for entry in report["excluded"]}
    assert set(excluded) == PENDING
    assert all("review pending" in reason for reason in excluded.values())


def test_unknown_source_set_is_rejected(staged_project: Path) -> None:
    settings = Settings(root=staged_project)
    with pytest.raises(ConfigError, match="unknown source set"):
        settings.resolve_source_set("beta")


def test_requesting_an_excluded_source_fails_loudly(staged_project: Path) -> None:
    settings = Settings(root=staged_project)
    with pytest.raises(ConfigError, match="excludes autodiag"):
        settings.resolve_source_set("public", ["obdex", "autodiag"])

    allowed, _ = settings.resolve_source_set("public", ["obdex"])
    assert allowed == ["obdex"]


def test_a_source_can_be_marked_not_redistributable(tmp_path: Path) -> None:
    root = create_project(tmp_path / "no-redistribution")
    config = root / "config" / "sources.yaml"
    text = config.read_text(encoding="utf-8")
    # OBDex is CC0 and approved; flip only the redistribution flag
    # the first source in the registry is OBDex
    text = text.replace("redistribution_allowed: true", "redistribution_allowed: false", 1)
    config.write_text(text, encoding="utf-8")

    settings = Settings(root=root)
    assert "obdex" not in settings.source_set_slugs("public")
    assert "obdex" in settings.source_set_slugs("private")


# ---------------------------------------------------------------------------
# build level
# ---------------------------------------------------------------------------

def test_private_build_keeps_every_source(staged_project: Path) -> None:
    settings = Settings(root=staged_project)
    result = build_database(settings, version="0.1.0", app_bundle=False, source_set="private")

    assert result.test_status == "passed"
    assert set(_claim_sources(result.database_path)) >= APPROVED | PENDING
    assert result.sources_excluded == []

    # the licence gate warns in a private build instead of blocking
    licence = {c.check_id: c for c in result.checks}["D007_licence_review"]
    assert licence.passed is False
    assert licence.blocking is False
    assert failed_blocking(result.checks) == []

    library = {c.check_id: c for c in result.checks}["D011_public_source_set"]
    assert library.passed is False
    assert library.blocking is False  # not a public build, so it is informational


def test_public_build_drops_unapproved_sources(staged_project: Path) -> None:
    settings = Settings(root=staged_project)
    result = build_database(settings, version="0.2.0", app_bundle=True, source_set="public")

    assert result.test_status == "passed", result.warnings
    assert result.source_set == "public"
    assert {entry["slug"] for entry in result.sources_excluded} == PENDING

    sources = _claim_sources(result.database_path)
    assert set(sources) == APPROVED | LOCAL, (
        f"unapproved source leaked into the public build: {sources}"
    )
    assert not (set(sources) & PENDING)
    assert sources["obdex"] > 0 and sources["wal33d"] > 0

    # and the data itself is gone, not merely untracked
    conn = connect(result.database_path, readonly=True)
    try:
        assert conn.execute("SELECT COUNT(*) FROM pids WHERE scope = 'vehicle'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM data_sources WHERE slug IN ('autodiag', 'obdb')"
        ).fetchone()[0] == 0
        # obdex is the only source of causes/repairs/symptoms in this set
        assert conn.execute("SELECT COUNT(*) FROM dtc_causes").fetchone()[0] > 0
        assert conn.execute("SELECT COUNT(*) FROM dtc_repairs").fetchone()[0] > 0
    finally:
        conn.close()

    checks = {c.check_id: c for c in result.checks}
    assert checks["D007_licence_review"].blocking is True
    assert checks["D007_licence_review"].passed is True
    assert checks["D011_public_source_set"].blocking is True
    assert checks["D011_public_source_set"].passed is True


def test_public_build_is_marked_in_the_database_and_manifest(staged_project: Path) -> None:
    settings = Settings(root=staged_project)
    result = build_database(settings, version="0.2.1", app_bundle=False, source_set="public")
    assert result.test_status == "passed"

    assert result.export_path is not None
    conn = sqlite3.connect(result.export_path)
    try:
        row = conn.execute(
            "SELECT source_set, test_status FROM db_versions WHERE version = '0.2.1'"
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == "public"
    assert row[1] == "passed"
    assert result.manifest_path is not None


def test_public_build_can_be_limited_further(staged_project: Path) -> None:
    settings = Settings(root=staged_project)
    result = build_database(
        settings, version="0.2.2", app_bundle=False, source_set="public", slugs=["wal33d"]
    )
    assert result.test_status == "passed"
    assert set(_claim_sources(result.database_path)) == {"wal33d"} | LOCAL


# ---------------------------------------------------------------------------
# gate and bundle level (defence in depth)
# ---------------------------------------------------------------------------

def test_gate_detects_a_leak_in_a_private_database(staged_project: Path) -> None:
    """If a filtered build ever regressed, D011 fails it."""
    settings = Settings(root=staged_project)
    private = build_database(settings, version="0.3.0", app_bundle=False, source_set="private")
    assert private.test_status == "passed"

    conn = connect(private.database_path, readonly=True)
    try:
        checks = {c.check_id: c for c in run_database_checks(conn, source_set="public")}
    finally:
        conn.close()
    assert checks["D011_public_source_set"].passed is False
    assert checks["D011_public_source_set"].blocking is True
    assert checks["D011_public_source_set"].count >= 2
    assert checks["D007_licence_review"].passed is False


def test_bundle_guard_refuses_unlicensed_data(staged_project: Path, tmp_path: Path) -> None:
    settings = Settings(root=staged_project)
    private = build_database(settings, version="0.3.1", app_bundle=False, source_set="private")
    assert private.export_path is not None

    conn = connect(private.export_path, readonly=True)
    try:
        assert set(unlicensed_sources(conn)) == PENDING
        with pytest.raises(LicenceError, match="autodiag"):
            assert_public_safe(conn)
    finally:
        conn.close()

    # a private bundle of the same file is produced, and records the set it used
    bundle = build_app_bundle(
        private.export_path, tmp_path / "app-private.sqlite", version="0.3.1",
        source_set="private",
    )
    assert bundle.source_set == "private"
    assert set(bundle.sources) >= APPROVED | PENDING

    # asking for a public bundle of an unlicensed file is refused outright
    with pytest.raises(LicenceError):
        build_app_bundle(
            private.export_path, tmp_path / "app-public.sqlite", version="0.3.1",
            source_set="public",
        )
    assert not (tmp_path / "app-public.sqlite").exists()


def test_public_bundle_contains_only_approved_sources(staged_project: Path) -> None:
    settings = Settings(root=staged_project)
    result = build_database(settings, version="0.4.0", app_bundle=True, source_set="public")
    assert result.test_status == "passed"
    assert result.app_bundle_path is not None

    conn = connect(result.app_bundle_path, readonly=True)
    try:
        slugs = {row[0] for row in conn.execute("SELECT slug FROM data_sources")}
        assert slugs == APPROVED | LOCAL
        metadata = conn.execute(
            "SELECT source_set FROM db_versions WHERE notes LIKE 'mobile app bundle%'"
        ).fetchone()
        assert metadata[0] == "public"
        assert conn.execute("SELECT COUNT(*) FROM provenance_summary").fetchone()[0] > 0
    finally:
        conn.close()


def test_public_and_private_artifacts_have_distinct_names(staged_project: Path) -> None:
    settings = Settings(root=staged_project)
    private = build_database(settings, version="0.9.0", app_bundle=False, source_set="private")
    public = build_database(settings, version="0.9.0", app_bundle=False, source_set="public")

    assert private.test_status == "passed" and public.test_status == "passed"
    assert private.export_path is not None and public.export_path is not None
    assert private.export_path.name == "autodoctor-0.9.0.sqlite"
    assert public.export_path.name == "autodoctor-0.9.0-public.sqlite"
    assert private.manifest_path != public.manifest_path

    import json

    private_manifest = json.loads(private.manifest_path.read_text())
    public_manifest = json.loads(public.manifest_path.read_text())
    assert private_manifest["source_set"] == "private"
    assert public_manifest["source_set"] == "public"
    assert {entry["slug"] for entry in public_manifest["sources_excluded"]} == PENDING
    assert private_manifest["sources_excluded"] == []
    assert public_manifest["counts"]["pids"] < private_manifest["counts"]["pids"]
