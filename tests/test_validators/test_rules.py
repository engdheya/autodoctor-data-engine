"""Validation rules: what blocks a release and what is only reported."""

from __future__ import annotations

from autodoctor_data_engine.models import (
    Context,
    Definition,
    NormalizedDtc,
    NormalizedPid,
    Provenance,
    Repair,
)
from autodoctor_data_engine.validators import (
    BLOCKING_RULES,
    blockable_errors,
    summarize,
    validate_record,
)


def provenance(**overrides) -> Provenance:
    base = {
        "source_slug": "obdex",
        "source_commit": "a" * 40,
        "file_path": "data/generic/P0xxx_enriched.yaml",
        "source_record_id": "P0xxx_enriched.yaml#P0301",
        "raw_hash": "0" * 64,
        "ingested_at": "2026-01-01T00:00:00Z",
    }
    base.update(overrides)
    return Provenance(**base)


def make_dtc(**overrides) -> NormalizedDtc:
    base = {
        "code": "P0301",
        "standard": "sae_j2012",
        "protocol": "obd2",
        "category": "powertrain",
        "context": Context(type="generic"),
        "definitions": [Definition(language="en", title="Cylinder 1 Misfire Detected",
                                   description="Misfire detected on cylinder 1.")],
        "provenance": provenance(),
    }
    base.update(overrides)
    return NormalizedDtc(**base)


def failed(issues) -> set[str]:
    return {i.rule_id for i in issues if not i.passed}


def test_a_clean_record_passes_every_rule() -> None:
    issues = validate_record(make_dtc())
    assert failed(issues) == set()
    assert summarize(issues)["failed"] == 0


def test_invalid_code_is_a_blocking_error() -> None:
    issues = validate_record(make_dtc(code="P15O9"))
    assert "V001_code_format" in failed(issues)
    assert "V001_code_format" in BLOCKING_RULES
    assert blockable_errors(issues)


def test_missing_provenance_is_a_blocking_error() -> None:
    record = make_dtc()
    record.provenance = record.provenance.model_copy(update={"raw_hash": ""})
    issues = validate_record(record)
    assert "V006_provenance_complete" in failed(issues)
    assert "raw_hash" in next(i.message for i in issues if not i.passed)


def test_generic_context_with_vendor_standard_is_rejected() -> None:
    issues = validate_record(make_dtc(standard="manufacturer_specific"))
    assert "V007_context_integrity" in failed(issues)


def test_missing_definition_is_an_error_but_not_blocking() -> None:
    issues = validate_record(make_dtc(definitions=[]))
    assert "V003_definition_present" in failed(issues)
    assert "V003_definition_present" not in BLOCKING_RULES


def test_repair_range_and_negatives() -> None:
    bad_range = Repair(key="r", cost_min=500, cost_max=100)
    assert "V009_repair_range" in failed(validate_record(make_dtc(repairs=[bad_range])))

    negative = Repair(key="r", hours_min=-1, hours_max=2)
    assert "V010_numeric_non_negative" in failed(validate_record(make_dtc(repairs=[negative])))


def test_related_code_format_and_self_reference() -> None:
    assert "V008_related_format" in failed(validate_record(make_dtc(related_codes=["ZZZ"])))
    assert "V011_related_self_reference" in failed(
        validate_record(make_dtc(related_codes=["P0301"]))
    )


def test_category_contradiction_is_only_a_warning() -> None:
    issues = validate_record(make_dtc(category="body"))
    assert "V002_category_consistent" in failed(issues)
    assert not blockable_errors(issues)


def test_short_definition_is_only_a_warning() -> None:
    issues = validate_record(
        make_dtc(definitions=[Definition(language="en", title="X1")])
    )
    assert "V004_definition_meaningful" in failed(issues)
    assert not blockable_errors(issues)


def test_unknown_standard_is_a_warning() -> None:
    issues = validate_record(make_dtc(standard="unknown"))
    assert "V012_standard_known" in failed(issues)


def test_vendor_prefix_inside_the_generic_layer_is_flagged() -> None:
    issues = validate_record(make_dtc(code="P1690"))
    assert "V020_prefix_scope_mismatch" in failed(issues)
    # ... but not when the code lives in a manufacturer context
    manufacturer = make_dtc(
        code="P1690",
        standard="manufacturer_specific",
        context=Context(type="manufacturer", manufacturer="Ford"),
    )
    assert "V020_prefix_scope_mismatch" not in failed(validate_record(manufacturer))


def test_pid_rules() -> None:
    pid = NormalizedPid(
        mode="01", pid="0C", scope="generic", names={"en": "Engine RPM"}, provenance=provenance()
    )
    assert failed(validate_record(pid)) == set()

    broken = NormalizedPid(mode="1", pid="ZZ", scope="generic", provenance=provenance())
    assert "V014_pid_format" in failed(validate_record(broken))
    assert blockable_errors(validate_record(broken))


def test_uds_code_declared_as_obd_is_flagged() -> None:
    record = make_dtc(code="0F4231", standard="uds", protocol="obd2")
    assert "V013_uds_with_obd_context" in failed(validate_record(record))


def test_summary_counts() -> None:
    issues = validate_record(make_dtc(code="P15O9", category="body"))
    summary = summarize(issues)
    assert summary["failed"] >= 2
    assert summary["errors"] >= 1
    assert summary["warnings"] >= 1
    assert summary["total"] == summary["passed"] + summary["failed"]
