"""Conflict detection: disagreement is preserved, never resolved by majority."""

from __future__ import annotations

import pytest

from autodoctor_data_engine.config import Settings
from autodoctor_data_engine.conflict_resolution import detect_conflicts
from autodoctor_data_engine.models import (
    Cause,
    Context,
    Definition,
    Flags,
    NormalizedDtc,
    Provenance,
)
from autodoctor_data_engine.staging import load_all_bundles


@pytest.fixture(scope="module")
def records(imported: Settings) -> list[NormalizedDtc]:
    return [r for b in load_all_bundles(imported) for r in b.records if isinstance(r, NormalizedDtc)]


def _record(slug: str, text: str, *, code: str = "P0420", **kwargs) -> NormalizedDtc:
    return NormalizedDtc(
        code=code,
        standard="sae_j2012",
        context=Context(type="generic"),
        definitions=[Definition(language="en", title=text)],
        provenance=Provenance(
            source_slug=slug,
            source_commit="a" * 40,
            file_path=f"{slug}.yaml",
            source_record_id=f"{slug}:{code}",
            raw_hash="0" * 64,
            ingested_at="2026-01-01T00:00:00Z",
        ),
        **kwargs,
    )


def test_fixture_conflict_is_detected(records, settings: Settings) -> None:
    conflicts, stats = detect_conflicts(records, settings.rules)
    p0420 = [c for c in conflicts if c.code == "P0420"]
    assert p0420, "the autodiag fixture deliberately disagrees with OBDex about P0420"
    conflict = p0420[0]
    assert conflict.conflict_type == "definition_disagreement"
    assert conflict.context_key.startswith("P0420|")
    sources = {e.source_slug for e in conflict.evidence}
    assert {"obdex", "autodiag"} <= sources
    assert conflict.similarity is not None and conflict.similarity < settings.rules.similarity_threshold
    assert stats["definition_disagreement"] >= 1


def test_agreeing_sources_produce_no_conflict(records, settings: Settings) -> None:
    conflicts, _ = detect_conflicts(records, settings.rules)
    assert not [c for c in conflicts if c.code == "P0301"]


def test_same_code_in_two_manufacturer_contexts_is_not_a_conflict(
    records, settings: Settings
) -> None:
    conflicts, _ = detect_conflicts(records, settings.rules)
    assert not [c for c in conflicts if c.code == "P1690"]


def test_one_conflict_per_code_instead_of_a_pair_matrix(settings: Settings) -> None:
    a = _record("obdex", "Catalyst System Efficiency Below Threshold")
    b = _record("wal33d", "Catalyst System Efficiency Below Threshold Bank 1")
    c = _record("autodiag", "Oxygen Sensor Heater Circuit Malfunction")
    conflicts, _ = detect_conflicts([a, b, c], settings.rules)
    assert len(conflicts) == 1
    # b is close enough to a to share its cluster, so only the two clusters are evidenced
    assert len(conflicts[0].evidence) == 2


def test_same_source_variants_are_not_reported_as_source_conflicts(settings: Settings) -> None:
    a = _record("obdex", "Catalyst System Efficiency Below Threshold")
    b = _record("obdex", "Completely different wording about the catalyst")
    conflicts, stats = detect_conflicts([a, b], settings.rules)
    assert conflicts == []
    assert stats["same_source_variants"] == 1


def test_cause_likelihood_disagreement_is_reported(settings: Settings) -> None:
    a = _record("obdex", "Misfire detected", code="P0301",
                causes=[Cause(key="spark_plug", likelihood="high", labels={"en": "Spark plug"})])
    b = _record("wal33d", "Misfire detected", code="P0301",
                causes=[Cause(key="spark_plug", likelihood="low", labels={"en": "Spark plug"})])
    conflicts, _ = detect_conflicts([a, b], settings.rules)
    likelihood = [c for c in conflicts if c.conflict_type == "cause_likelihood_disagreement"]
    assert likelihood
    assert "spark_plug" in likelihood[0].attribute


def test_flag_disagreement_is_reported(settings: Settings) -> None:
    a = _record("obdex", "Catalyst efficiency", flags=Flags(mil=True))
    b = _record("wal33d", "Catalyst efficiency", flags=Flags(mil=False))
    conflicts, _ = detect_conflicts([a, b], settings.rules)
    flags = [c for c in conflicts if c.conflict_type == "flag_disagreement"]
    assert flags and flags[0].attribute == "flags.mil"
