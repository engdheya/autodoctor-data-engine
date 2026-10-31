"""The extraction pipeline: raw preservation, staging, validation, failure modes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from helpers import create_project

from autodoctor_data_engine.config import ConfigError, Settings
from autodoctor_data_engine.models import parse_record
from autodoctor_data_engine.pipeline import (
    ImportRejected,
    import_source,
    inspect_sources,
    validate_staged,
)
from autodoctor_data_engine.utils.hashing import sha256_file
from autodoctor_data_engine.utils.jsonl import read_jsonl


def test_inspection_reports_all_sources(fresh_project: Path) -> None:
    settings = Settings(root=fresh_project)
    inspections = inspect_sources(settings)
    assert {i.slug for i in inspections} == {"obdex", "wal33d", "autodiag", "obdb"}
    assert all(i.present for i in inspections)
    obdex = next(i for i in inspections if i.slug == "obdex")
    assert obdex.layout["dtc_entries"] == 3


def test_inspection_tolerates_a_missing_checkout(tmp_path) -> None:
    settings = Settings(root=create_project(tmp_path / "p", with_upstream=False))
    inspections = inspect_sources(settings)
    assert inspections
    assert all(not i.present for i in inspections)
    assert all(i.warnings for i in inspections)


def test_import_writes_raw_archive_and_staging(fresh_project: Path) -> None:
    settings = Settings(root=fresh_project)
    result = import_source(settings, "obdex")

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["record_counts"] == {"dtc": 3, "pid": 2}
    assert manifest["stats"]["raw_records"] == 5
    assert manifest["content_hash"]
    assert len(manifest["files"]) == 2

    raw_dtc = Path(fresh_project) / manifest["raw_archive"] / "dtc.jsonl"
    assert raw_dtc.is_file()
    raw_rows = list(read_jsonl(raw_dtc))
    assert len(raw_rows) == 3
    assert raw_rows[0]["payload"]["code"] == "P0301"  # verbatim upstream shape

    staging_dir = result.manifest_path.parent
    normalized = [parse_record(row) for row in read_jsonl(staging_dir / "normalized.jsonl")]
    assert len(normalized) == 5
    assert (staging_dir / "validation.jsonl").is_file()

    # provenance of every staged record is complete
    for record in normalized:
        assert record.provenance.source_slug == "obdex"
        assert record.provenance.source_commit
        assert record.provenance.raw_hash
        assert record.provenance.file_path.startswith("data/")


def test_import_never_modifies_the_upstream_files(fresh_project: Path) -> None:
    settings = Settings(root=fresh_project)
    upstream_file = settings.sources["obdex"].local_path / "data" / "generic" / "P0xxx_enriched.yaml"
    before = sha256_file(upstream_file)
    import_source(settings, "obdex")
    assert sha256_file(upstream_file) == before


def test_fail_on_error_aborts_on_invalid_data(fresh_project: Path) -> None:
    settings = Settings(root=fresh_project)
    bad_file = settings.sources["autodiag"].local_path / "data-src" / "ecu" / "generic" / "audi" / "codes" / "P15O9.yml"
    bad_file.write_text(
        "code: P15O9\ndefinition: Typo in a code\nstandard: [saej2012.2002]\n"
        "protocol: [obd2]\nevidence: [obdcodex]\n",
        encoding="utf-8",
    )
    with pytest.raises(ImportRejected) as excinfo:
        import_source(settings, "autodiag", fail_on_error=True)
    assert excinfo.value.rejected >= 1
    assert excinfo.value.samples[0]["rules"] == ["V001_code_format"]

    # the same import succeeds when the caller accepts quarantining
    result = import_source(settings, "autodiag")
    assert result.rejected == 1


def test_validate_staged_summarizes(imported: Settings) -> None:
    summary = validate_staged(imported)
    assert set(summary["sources"]) == {"obdex", "wal33d", "autodiag", "obdb"}
    assert summary["totals"]["records"] > 0
    assert summary["totals"]["rejected"] == 0


def test_import_is_idempotent(fresh_project: Path) -> None:
    settings = Settings(root=fresh_project)
    first = import_source(settings, "wal33d")
    second = import_source(settings, "wal33d")
    assert first.content_hash == second.content_hash
    assert first.records_normalized == second.records_normalized


def test_unknown_source_is_rejected(fresh_project: Path) -> None:
    settings = Settings(root=fresh_project)
    with pytest.raises(ConfigError, match="unknown source"):
        import_source(settings, "nope")
