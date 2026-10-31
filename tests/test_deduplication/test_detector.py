"""Duplicate detection must distinguish "same statement" from "same code"."""

from __future__ import annotations

import pytest

from autodoctor_data_engine.config import Settings
from autodoctor_data_engine.deduplication import detect_duplicates
from autodoctor_data_engine.models import NormalizedDtc
from autodoctor_data_engine.staging import load_all_bundles


@pytest.fixture(scope="module")
def records(imported: Settings) -> list[NormalizedDtc]:
    bundles = load_all_bundles(imported)
    return [r for b in bundles for r in b.records if isinstance(r, NormalizedDtc)]


def test_exact_duplicate_across_three_sources(records, settings: Settings) -> None:
    groups, stats = detect_duplicates(records, settings.rules)
    p0301 = [
        g for g in groups
        if g.match_type == "exact_statement" and "P0301" in g.group_key + g.reason
    ]
    assert p0301, "P0301 is stated identically by obdex, wal33d and autodiag"
    group = p0301[0]
    assert len(group.members) >= 3
    assert group.similarity == 1.0
    assert {m.split(":")[0] for m in group.members} == {"obdex", "wal33d", "autodiag"}


def test_punctuation_only_differences_collapse_to_one_statement(
    records, settings: Settings
) -> None:
    """"Threshold (Bank 1)" and "Threshold Bank 1" are the same statement."""
    groups, _ = detect_duplicates(records, settings.rules)
    p0420 = [g for g in groups if g.match_type == "exact_statement" and "P0420" in g.reason]
    assert p0420
    assert {m.split(":")[0] for m in p0420[0].members} == {"obdex", "wal33d"}


def test_near_duplicates_are_reported_but_never_merged(settings: Settings) -> None:
    from autodoctor_data_engine.models import Context, Definition, NormalizedDtc, Provenance

    def record(slug: str, title: str) -> NormalizedDtc:
        return NormalizedDtc(
            code="P0420",
            standard="sae_j2012",
            context=Context(type="generic"),
            definitions=[Definition(language="en", title=title)],
            provenance=Provenance(
                source_slug=slug,
                source_commit="a" * 40,
                file_path=f"{slug}.yaml",
                source_record_id=f"{slug}:P0420",
                raw_hash="0" * 64,
                ingested_at="2026-01-01T00:00:00Z",
            ),
        )

    groups, stats = detect_duplicates(
        [
            record("obdex", "Catalyst System Efficiency Below Threshold Bank 1"),
            record("wal33d", "Catalyst System Efficiency Below Threshold (Bank 1) Reduced"),
        ],
        settings.rules,
    )
    near = [g for g in groups if g.match_type == "near_statement"]
    assert near
    group = near[0]
    assert settings.rules.similarity_threshold <= group.similarity < 1.0
    assert len(group.members) == 2  # both statements survive, one is only flagged
    assert stats["near"] == 1


def test_same_code_in_different_contexts_is_not_a_duplicate(records, settings: Settings) -> None:
    groups, _ = detect_duplicates(records, settings.rules)
    variant = [g for g in groups if g.match_type == "code_context_variants"
               and "P1690" in g.group_key + g.reason]
    assert variant
    group = variant[0]
    assert len(group.members) == 2
    assert all("|manufacturer:" in member for member in group.members)
    assert "must not be merged" in group.reason


def test_duplicate_statistics_are_consistent(records, settings: Settings) -> None:
    groups, stats = detect_duplicates(records, settings.rules)
    assert stats["exact"] == sum(1 for g in groups if g.match_type == "exact_statement")
    assert stats["near"] == sum(1 for g in groups if g.match_type == "near_statement")
    assert stats["context_variants"] == sum(
        1 for g in groups if g.match_type == "code_context_variants"
    )
    assert stats["statements"] > 0


def test_vehicle_source_contributes_no_dtc_statements(records, settings: Settings) -> None:
    """OBDb carries no DTC definitions, so it may not appear in a statement group."""
    groups, _ = detect_duplicates(records, settings.rules)
    statement_groups = [g for g in groups if g.match_type != "code_context_variants"]
    assert not any(member.startswith("obdb:") for g in statement_groups for member in g.members)
