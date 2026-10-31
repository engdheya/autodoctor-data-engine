"""Provenance must answer "where did this come from" for every statement."""

from __future__ import annotations

from autodoctor_data_engine.provenance import ProvenanceTracker


def test_explain_returns_all_contexts(db_conn) -> None:
    tracker = ProvenanceTracker(db_conn)
    payload = tracker.explain_code("P1690")
    assert payload["found"]
    assert len(payload["contexts"]) == 2
    manufacturers = {context["manufacturer"] for context in payload["contexts"]}
    assert manufacturers == {"BMW", "Ford"}


def test_every_definition_has_a_source_with_commit_and_licence(db_conn) -> None:
    tracker = ProvenanceTracker(db_conn)
    payload = tracker.explain_code("P0301")
    definitions = payload["contexts"][0]["definitions"]
    assert definitions
    for definition in definitions:
        assert definition["claims"], "a definition without provenance must never exist"
        for claim in definition["claims"]:
            assert claim["source"]
            assert claim["commit_sha"]
            assert claim["data_license"]
            assert claim["extracted_at"]
            if claim["is_translated"]:
                # a human translation has no upstream file, only a translator record
                assert claim["source"] == "local-translations"
            else:
                assert claim["file_path"]
    sources = {claim["source"] for d in definitions for claim in d["claims"]}
    assert {"obdex", "wal33d", "autodiag"} <= sources


def test_explain_reports_conflicts(db_conn) -> None:
    tracker = ProvenanceTracker(db_conn)
    payload = tracker.explain_code("P0420")
    conflicts = payload["contexts"][0]["conflicts"]
    assert conflicts
    assert any(c["type"] == "definition_disagreement" for c in conflicts)
    assert conflicts[0]["evidence"]


def test_explain_unknown_code(db_conn) -> None:
    tracker = ProvenanceTracker(db_conn)
    payload = tracker.explain_code("P9999")
    assert payload["found"] is False
    assert payload["contexts"] == []


def test_source_summary_lists_every_source_with_commit(db_conn) -> None:
    tracker = ProvenanceTracker(db_conn)
    summary = {row["slug"]: row for row in tracker.source_summary()}
    assert {"obdex", "wal33d", "autodiag", "obdb"} <= set(summary)
    assert all(row["commit_sha"] for row in summary.values())
    assert summary["autodiag"]["legal_review_status"] == "pending"
    assert summary["autodiag"]["share_alike"] == 1


def test_verification_breakdown(db_conn) -> None:
    tracker = ProvenanceTracker(db_conn)
    breakdown = tracker.verification_breakdown()
    assert set(breakdown["definitions"]) <= {
        "verified", "source_reported", "conflicting", "unverified"
    }
    assert breakdown["definitions"].get("verified", 0) >= 1
    assert breakdown["definitions"].get("conflicting", 0) >= 1
