"""The intermediate models enforce the invariants the pipeline relies on."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from autodoctor_data_engine.models import (
    Context,
    Definition,
    NormalizedDtc,
    NormalizedPid,
    Provenance,
    parse_record,
)


def provenance() -> Provenance:
    return Provenance(
        source_slug="obdex",
        source_commit="a" * 40,
        file_path="data/generic/P0xxx_enriched.yaml",
        source_record_id="P0xxx_enriched.yaml#P0301",
        raw_hash="0" * 64,
        ingested_at="2026-01-01T00:00:00Z",
    )


def test_context_requires_its_target() -> None:
    with pytest.raises(ValidationError):
        Context(type="manufacturer")
    with pytest.raises(ValidationError):
        Context(type="ecu")
    with pytest.raises(ValidationError):
        Context(type="vehicle_variant")


def test_generic_context_must_be_empty() -> None:
    with pytest.raises(ValidationError):
        Context(type="generic", manufacturer="Ford")


def test_context_key_is_stable_and_contextual() -> None:
    generic = NormalizedDtc(
        code="P1690",
        standard="sae_j2012",
        context=Context(type="generic"),
        definitions=[Definition(language="en", title="Mil lamp")],
        provenance=provenance(),
    )
    ford = NormalizedDtc(
        code="P1690",
        standard="manufacturer_specific",
        context=Context(type="manufacturer", manufacturer="Ford"),
        definitions=[Definition(language="en", title="Wastegate")],
        provenance=provenance(),
    )
    assert generic.context_key == "P1690|sae_j2012|generic:generic"
    assert ford.context_key == "P1690|manufacturer_specific|manufacturer:ford"
    assert generic.context_key != ford.context_key


def test_definition_emptiness() -> None:
    assert Definition(language="en").is_empty()
    assert Definition(language="en", title="  ").is_empty()
    assert not Definition(language="en", title="Misfire").is_empty()


def test_parse_record_dispatches_on_type() -> None:
    payload = {
        "record_type": "pid",
        "mode": "01",
        "pid": "0C",
        "scope": "generic",
        "names": {"en": "RPM"},
        "provenance": provenance().model_dump(),
    }
    record = parse_record(payload)
    assert isinstance(record, NormalizedPid)

    with pytest.raises(ValueError):
        parse_record({"record_type": "unknown"})


def test_invalid_enum_is_rejected() -> None:
    with pytest.raises(ValidationError):
        NormalizedPid(
            mode="01", pid="0C", scope="nonsense", provenance=provenance()
        )
