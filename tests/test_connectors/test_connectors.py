"""Each connector must read its upstream layout as it really is.

These tests run against fixture checkouts that mirror the real repositories
(file names, directory nesting, field names).
"""

from __future__ import annotations

import pytest

from autodoctor_data_engine.config import Settings
from autodoctor_data_engine.connectors import build_connector
from autodoctor_data_engine.connectors.obdb import split_repo_name
from autodoctor_data_engine.models import NormalizedDtc, NormalizedEcu, NormalizedPid, NormalizedVehicle


@pytest.fixture
def obdex(settings: Settings):
    return build_connector(settings, "obdex")


@pytest.fixture
def wal33d(settings: Settings):
    return build_connector(settings, "wal33d")


@pytest.fixture
def autodiag(settings: Settings):
    return build_connector(settings, "autodiag")


@pytest.fixture
def obdb(settings: Settings):
    return build_connector(settings, "obdb")


# ---------------------------------------------------------------------------
# OBDex: YAML with bilingual prose, causes, symptoms, repairs
# ---------------------------------------------------------------------------

def test_obdex_inspection(obdex) -> None:
    inspection = obdex.inspect()
    assert inspection.present
    assert inspection.layout["dtc_entries"] == 3
    assert inspection.layout["bilingual"] == ["en", "de"]
    assert inspection.licence["data"] == "CC0-1.0"


def test_obdex_extracts_every_record(obdex) -> None:
    raw = list(obdex.extract())
    assert len(raw) == 5  # 3 DTC + 2 PID
    assert sorted({r.record_type for r in raw}) == ["dtc", "pid"]
    assert raw[0].source_record_id.startswith("P0xxx_enriched.yaml#P")


def test_obdex_normalizes_rich_content(obdex) -> None:
    raw = next(r for r in obdex.extract() if r.source_record_id.endswith("#P0301"))
    (record,) = obdex.normalize(raw, obdex.provenance_base(raw, "a" * 40))
    assert isinstance(record, NormalizedDtc)
    assert record.code == "P0301"
    assert record.context.type == "generic"
    assert record.standard == "sae_j2012"
    assert record.category == "powertrain"

    languages = {d.language for d in record.definitions}
    assert languages == {"en", "de"}
    en = next(d for d in record.definitions if d.language == "en")
    assert en.title == "Cylinder 1 Misfire Detected"
    assert "crankshaft" in (en.description or "")

    assert {c.key for c in record.causes} == {"spark_plug_worn", "ignition_coil_faulty"}
    assert next(c for c in record.causes if c.key == "spark_plug_worn").likelihood == "high"
    assert len(record.symptoms) == 2
    assert len(record.components) == 3
    assert record.related_codes == ["P0300", "P0302", "P0304"]

    repair = record.repairs[0]
    assert repair.cost_min == 40 and repair.cost_max == 300
    assert repair.currency == "EUR"
    assert repair.difficulty == "medium"
    assert repair.diy_possible is True

    assert record.flags.mil is True
    assert record.flags.emissions_relevant is True
    assert record.flags.limp_mode_possible is True
    assert record.references == ["sae:J2012"]
    assert len(record.evidence_urls) == 2


def test_obdex_pid_normalization(obdex) -> None:
    raw = next(r for r in obdex.extract() if r.record_type == "pid")
    (pid,) = obdex.normalize(raw, obdex.provenance_base(raw, "a" * 40))
    assert isinstance(pid, NormalizedPid)
    assert pid.mode == "01"
    assert pid.scope == "generic"
    assert pid.names["en"] == "Engine RPM"
    assert pid.names["de"] == "Motordrehzahl"
    assert pid.unit == "rpm"


# ---------------------------------------------------------------------------
# Wal33D: compiled SQLite + raw text lists
# ---------------------------------------------------------------------------

def test_wal33d_inspection_reads_the_database(wal33d) -> None:
    inspection = wal33d.inspect()
    assert inspection.layout["rows"] == 5
    assert inspection.layout["unique_codes"] == 4
    assert "FORD" in inspection.layout["manufacturers"]
    # the text lists are fewer than the compiled rows; that must be surfaced
    assert any("text lists" in w for w in inspection.warnings)


def test_wal33d_extracts_sqlite_rows(wal33d) -> None:
    raw = list(wal33d.extract())
    assert len(raw) == 5
    assert {r.payload["source_file"] for r in raw} == {"p_codes", "ford_codes", "bmw_codes"}


def test_wal33d_generic_row_becomes_a_generic_context(wal33d) -> None:
    raw = next(r for r in wal33d.extract() if r.source_record_id.startswith("P0301"))
    (record,) = wal33d.normalize(raw, wal33d.provenance_base(raw, "b" * 40))
    assert record.context.type == "generic"
    assert record.standard == "sae_j2012"
    assert record.definitions[0].title == "Cylinder 1 Misfire Detected"


def test_wal33d_manufacturer_rows_keep_their_manufacturer(wal33d) -> None:
    records = []
    for raw in wal33d.extract():
        if raw.source_record_id.startswith("P1690"):
            records.extend(wal33d.normalize(raw, wal33d.provenance_base(raw, "b" * 40)))
    assert {r.context.manufacturer for r in records} == {"Ford", "BMW"}
    assert {r.standard for r in records} == {"manufacturer_specific"}
    # the same code in two manufacturer contexts is two identities
    assert len({r.context_key for r in records}) == 2


# ---------------------------------------------------------------------------
# autodiag2: one YAML file per (code, context)
# ---------------------------------------------------------------------------

def test_autodiag_inspection(autodiag) -> None:
    inspection = autodiag.inspect()
    assert inspection.layout["code_files"] == 4
    assert inspection.layout["diagnostics"]["empty_definition"] == 0
    assert inspection.layout["standards"] == {"saej2012.2002": 4}


def test_autodiag_extracts_dtc_ecu_and_vehicle(autodiag) -> None:
    records = list(autodiag.extract())
    kinds = {r.record_type for r in records}
    assert kinds == {"dtc", "ecu", "vehicle"}
    assert sum(1 for r in records if r.record_type == "dtc") == 4


def test_autodiag_context_from_path(autodiag) -> None:
    contexts = {}
    for raw in autodiag.extract():
        if raw.record_type != "dtc":
            continue
        (record,) = autodiag.normalize(raw, autodiag.provenance_base(raw, "c" * 40))
        contexts[record.code] = record

    assert contexts["P1641"].context.type == "manufacturer"
    assert contexts["P1641"].context.manufacturer == "Audi"
    assert contexts["P1641"].standard == "sae_j2012"
    assert contexts["P1113"].context.type == "ecu"
    assert contexts["P1113"].context.ecu == "Bosch EDC16C34"
    assert contexts["P0301"].context.type == "generic"


def test_autodiag_keeps_detection_conditions_as_tests(autodiag) -> None:
    raw = next(
        r for r in autodiag.extract()
        if r.record_type == "dtc" and r.source_record_id.endswith("saej2012.2002/codes/P0301.yml")
    )
    (record,) = autodiag.normalize(raw, autodiag.provenance_base(raw, "c" * 40))
    assert len(record.tests) == 1
    assert "two consecutive drive cycles" in record.tests[0].texts["en"]
    assert record.flags.mil is True
    assert record.flags.severity_label == "high"


def test_autodiag_separates_urls_from_bare_evidence(autodiag) -> None:
    raw = next(
        r for r in autodiag.extract()
        if r.record_type == "dtc" and r.source_record_id.endswith("saej2012.2002/codes/P0301.yml")
    )
    (record,) = autodiag.normalize(raw, autodiag.provenance_base(raw, "c" * 40))
    assert record.evidence_urls == ["https://example.org/obd-code-reference"]
    assert record.references == ["obdcodex"]


# ---------------------------------------------------------------------------
# OBDb: an organisation of vehicle repositories
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "repo, expected",
    [
        ("Toyota-Camry", ("Toyota", "Camry")),
        ("Mercedes-Benz-EQS-Class-Sedan", ("Mercedes-Benz", "EQS-Class-Sedan")),
        ("VauxhallOpel-Corsa-e", ("VauxhallOpel", "Corsa-e")),
        ("Tesla-Model-3", ("Tesla", "Model-3")),
    ],
)
def test_split_repo_name(repo, expected) -> None:
    assert split_repo_name(repo) == expected


def test_obdb_inspection_has_no_dtc(obdb) -> None:
    inspection = obdb.inspect()
    assert inspection.layout["dtc_definitions"] == 0
    assert inspection.layout["repositories"] == 1
    assert inspection.layout["signals"] == 2
    assert inspection.layout["detail"]["Toyota-Camry"]["generations"] == 2


def test_obdb_extracts_vehicles_ecus_and_parameters(obdb) -> None:
    records = list(obdb.extract())
    kinds = [r.record_type for r in records]
    assert kinds.count("vehicle") == 2
    assert kinds.count("ecu") == 2
    assert kinds.count("pid") == 2


def test_obdb_normalizes_vehicle_and_parameter(obdb) -> None:
    normalized = [
        obdb.normalize(raw, obdb.provenance_base(raw, "obdb:test"))
        for raw in obdb.extract()
    ]
    flat = [item for group in normalized for item in group]
    vehicle = next(r for r in flat if isinstance(r, NormalizedVehicle))
    assert vehicle.manufacturer == "Toyota"
    assert vehicle.model == "Camry"
    assert vehicle.generation == "Fifth Generation (XV30)"
    assert (vehicle.year_start, vehicle.year_end) == (2001, 2006)

    ecu = next(r for r in flat if isinstance(r, NormalizedEcu))
    assert ecu.header == "7E0"
    assert ecu.ecu_type == "engine"
    assert ecu.vehicle_variant == "Toyota Camry"

    pid = next(r for r in flat if isinstance(r, NormalizedPid))
    assert pid.scope == "vehicle"
    assert pid.mode == "22"
    assert pid.signal_id == "CAMRY_ENG_ODO"
    assert pid.unit == "kilometers"
