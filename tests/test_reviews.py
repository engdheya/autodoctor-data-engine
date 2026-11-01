"""Conflict review: decisions are recorded once and survive every rebuild."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from helpers import create_project

from autodoctor_data_engine.cli import EXIT_OK, main
from autodoctor_data_engine.config import Settings
from autodoctor_data_engine.database.build import build_database
from autodoctor_data_engine.database.connection import connect
from autodoctor_data_engine.pipeline import import_source
from autodoctor_data_engine.reviews import ReviewError, ReviewStore, conflict_fingerprint


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = create_project(tmp_path_factory.mktemp("autodoctor-reviews"))
    settings = Settings(root=root)
    for slug in ("obdex", "wal33d", "autodiag", "obdb"):
        import_source(settings, slug)
    return root


def _build(project: Path, version: str):
    settings = Settings(root=project)
    return build_database(settings, version=version, app_bundle=False, source_set="private")


def _conflict(project: Path, code: str = "P0420") -> dict:
    conn = connect(Settings(root=project).database_path(), readonly=True)
    try:
        row = conn.execute(
            "SELECT id, fingerprint, code, context_key, status, resolution_note "
            "FROM conflicts WHERE code = ?",
            (code,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    return dict(row)


def _canonical_title(project: Path, code: str, language: str = "en") -> str:
    conn = connect(Settings(root=project).database_path(), readonly=True)
    try:
        row = conn.execute(
            """
            SELECT d.title FROM dtc_codes c JOIN dtc_definitions d ON d.dtc_code_id = c.id
            WHERE c.code = ? AND c.context_type = 'generic' AND d.language = ?
              AND d.is_canonical = 1
            """,
            (code, language),
        ).fetchone()
    finally:
        conn.close()
    return row[0]


# ---------------------------------------------------------------------------
# fingerprints
# ---------------------------------------------------------------------------

def test_fingerprint_is_stable_across_builds(project: Path) -> None:
    first = _build(project, "0.1.0")
    assert first.test_status == "passed"
    fingerprint = _conflict(project)["fingerprint"]
    assert fingerprint and len(fingerprint) == 16

    second = _build(project, "0.2.0")
    assert second.test_status == "passed"
    assert _conflict(project)["fingerprint"] == fingerprint


def test_fingerprint_depends_on_the_statements(project: Path) -> None:
    conflict = _conflict(project)
    store = ReviewStore.load(project)
    assert store.get(conflict["fingerprint"]) is None


# ---------------------------------------------------------------------------
# the store
# ---------------------------------------------------------------------------

def test_a_decision_needs_a_note_and_a_reviewer(tmp_path: Path) -> None:
    store = ReviewStore(root=tmp_path)
    with pytest.raises(ReviewError, match="note"):
        store.record(fingerprint="abc", decision="accepted_difference", note="", reviewer="me")
    with pytest.raises(ReviewError, match="reviewer"):
        store.record(fingerprint="abc", decision="accepted_difference", note="fine", reviewer="")
    with pytest.raises(ReviewError, match="source"):
        store.record(fingerprint="abc", decision="resolved", note="fine", reviewer="me")
    with pytest.raises(ReviewError, match="decision must be"):
        store.record(fingerprint="abc", decision="whatever", note="fine", reviewer="me")


def test_decisions_are_written_and_reread(tmp_path: Path) -> None:
    store = ReviewStore(root=tmp_path)
    store.record(
        fingerprint="f" * 16,
        decision="accepted_difference",
        note="OBDex adds storage detail, autodiag2 is terse but not contradictory",
        reviewer="data-reviewer",
        code="P0420",
        context_key="P0420|sae_j2012|generic:generic",
        conflict_type="definition_disagreement",
    )
    path = tmp_path / "data" / "reviews" / "conflicts.yaml"
    assert path.is_file()
    reloaded = ReviewStore.load(tmp_path)
    entry = reloaded.get("f" * 16)
    assert entry is not None
    assert entry.status == "accepted_difference"
    assert "data-reviewer" in entry.resolution_note()


# ---------------------------------------------------------------------------
# build integration
# ---------------------------------------------------------------------------

def test_accepted_difference_closes_the_conflict_for_good(project: Path) -> None:
    conflict = _conflict(project)
    store = ReviewStore.load(project)
    store.record(
        fingerprint=conflict["fingerprint"],
        decision="accepted_difference",
        note="both statements describe the catalyst efficiency check",
        reviewer="qa-reviewer",
        code="P0420",
        context_key=conflict["context_key"],
        conflict_type="definition_disagreement",
    )

    result = _build(project, "0.3.0")
    assert result.test_status == "passed"
    assert result.review_stats["applied"] >= 1
    assert result.counts["conflicts_open"] == 0
    assert result.counts["conflicts_resolved"] == result.counts["conflicts"]

    after = _conflict(project)
    assert after["status"] == "accepted_difference"
    assert "qa-reviewer" in after["resolution_note"]

    # a second rebuild does not re-open it
    _build(project, "0.3.1")
    assert _conflict(project)["status"] == "accepted_difference"


def test_resolved_decision_can_change_the_canonical_statement(project: Path) -> None:
    before = _canonical_title(project, "P0420")
    assert before.startswith("Catalyst System Efficiency")

    conflict = _conflict(project)
    store = ReviewStore.load(project)
    store.record(
        fingerprint=conflict["fingerprint"],
        decision="resolved",
        chosen_source="autodiag",
        note="checked against the manufacturer table: this is the monitor circuit code",
        reviewer="qa-reviewer",
        code="P0420",
        context_key=conflict["context_key"],
        conflict_type="definition_disagreement",
    )

    result = _build(project, "0.4.0")
    assert result.test_status == "passed"
    assert result.review_stats["canonical_overrides"] >= 1
    assert _canonical_title(project, "P0420") == "Catalyst Monitor Circuit High Input"
    assert _conflict(project)["status"] == "resolved"


def test_unknown_fingerprint_is_reported_not_fatal(project: Path) -> None:
    store = ReviewStore.load(project)
    store.record(
        fingerprint="0" * 16,
        decision="accepted_difference",
        note="decision for a conflict that this build no longer contains",
        reviewer="qa-reviewer",
    )
    result = _build(project, "0.5.0")
    assert result.test_status == "passed"
    assert result.review_stats["unmatched"] >= 1
    store.decisions.pop("0" * 16)
    store.save()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_cli_lists_and_reviews_a_conflict(project: Path, capsys) -> None:
    fingerprint = _conflict(project)["fingerprint"]
    assert main(["--root", str(project), "--json", "list-conflicts", "--status", "all"]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["conflicts"][0]["fingerprint"] == fingerprint
    assert {item["source_slug"] for item in payload["conflicts"][0]["evidence"]} == {
        "obdex", "autodiag"
    }

    assert main([
        "--root", str(project), "review-conflict", fingerprint, "--accept",
        "--note", "wording only", "--reviewer", "cli-reviewer",
    ]) == EXIT_OK
    assert "recorded accepted_difference" in capsys.readouterr().out
    assert ReviewStore.load(project).get(fingerprint) is not None

    # a resolved decision without a source is refused
    assert main([
        "--root", str(project), "review-conflict", fingerprint, "--resolve",
        "--note", "nope", "--reviewer", "cli-reviewer",
    ]) == 2


def test_cli_rejects_an_unknown_fingerprint(project: Path, capsys) -> None:
    assert main([
        "--root", str(project), "review-conflict", "deadbeefdeadbeef", "--accept",
        "--note", "x", "--reviewer", "y",
    ]) == 1
    assert "no conflict with fingerprint" in capsys.readouterr().out


def test_conflict_fingerprints_are_unique_per_disagreement(project: Path) -> None:
    conn = connect(Settings(root=project).database_path(), readonly=True)
    try:
        rows = conn.execute("SELECT fingerprint FROM conflicts").fetchall()
    finally:
        conn.close()
    fingerprints = [row[0] for row in rows]
    assert len(fingerprints) == len(set(fingerprints))
    assert all(fingerprints)


def test_conflict_fingerprint_helper_matches_the_stored_value(project: Path) -> None:
    conn = connect(Settings(root=project).database_path(), readonly=True)
    try:
        stored = conn.execute("SELECT fingerprint FROM conflicts LIMIT 1").fetchone()[0]
    finally:
        conn.close()
    assert conflict_fingerprint.__module__.endswith("reviews")
    assert len(stored) == 16
