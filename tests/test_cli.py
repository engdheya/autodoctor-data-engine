"""The command line is the supported interface for the pipeline operators."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from helpers import create_project

from autodoctor_data_engine.cli import EXIT_FAILURE, EXIT_OK, main


@pytest.fixture(scope="module")
def cli_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = create_project(tmp_path_factory.mktemp("autodoctor-cli"))
    assert main(["--root", str(root), "inspect-sources"]) == EXIT_OK
    assert main(["--root", str(root), "import", "--all"]) == EXIT_OK
    assert main(["--root", str(root), "build-db", "--version", "0.1.0"]) == EXIT_OK
    return root


def test_inspect_sources_writes_a_report(cli_root: Path, capsys) -> None:
    assert main(["--root", str(cli_root), "inspect-sources"]) == EXIT_OK
    output = capsys.readouterr().out
    assert "obdex" in output and "commit:" in output
    assert (cli_root / "data" / "reports" / "source-inspection.json").is_file()


def test_version_reports_the_release(cli_root: Path, capsys) -> None:
    assert main(["--root", str(cli_root), "--json", "version"]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["release"]["version"] == "0.1.0"
    assert payload["release"]["test_status"] == "passed"
    assert len(payload["release"]["database_sha256"]) == 64
    assert {s["slug"] for s in payload["release"]["sources"]} == {
        "obdex", "wal33d", "autodiag", "obdb"
    }


def test_report_imports(cli_root: Path, capsys) -> None:
    assert main(["--root", str(cli_root), "report", "--imports"]) == EXIT_OK
    output = capsys.readouterr().out
    assert "Import report" in output
    assert "obdex" in output


def test_report_on_the_database(cli_root: Path, capsys) -> None:
    assert main(["--root", str(cli_root), "report", "--write"]) == EXIT_OK
    output = capsys.readouterr().out
    assert "Database contents" in output
    assert (cli_root / "data" / "reports" / "data-report.md").is_file()


def test_search_prints_a_diagnostic_card(cli_root: Path, capsys) -> None:
    assert main(["--root", str(cli_root), "search", "p0301"]) == EXIT_OK
    output = capsys.readouterr().out
    assert "P0301" in output
    assert "Cylinder 1 Misfire Detected" in output
    assert "AR:" in output
    assert "not a failed part" in output.replace("\n", " ")


def test_search_unknown_code_fails(cli_root: Path, capsys) -> None:
    assert main(["--root", str(cli_root), "search", "P9999"]) == EXIT_FAILURE
    assert "not found" in capsys.readouterr().out


def test_explain_shows_the_provenance_chain(cli_root: Path, capsys) -> None:
    assert main(["--root", str(cli_root), "explain", "P0301"]) == EXIT_OK
    output = capsys.readouterr().out
    assert "<- obdex @" in output
    assert "licence CC0-1.0" in output
    assert "status:" in output


def test_explain_json_is_machine_readable(cli_root: Path, capsys) -> None:
    assert main(["--root", str(cli_root), "--json", "explain", "P1690"]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["found"] is True
    assert len(payload["contexts"]) == 2


def test_detect_duplicates_and_conflicts(cli_root: Path, capsys) -> None:
    assert main(["--root", str(cli_root), "detect-duplicates", "--limit", "2"]) == EXIT_OK
    assert "duplicate groups" in capsys.readouterr().out

    assert main(["--root", str(cli_root), "detect-conflicts", "--limit", "2"]) == EXIT_OK
    assert "conflicts detected" in capsys.readouterr().out


def test_validate_summarizes(cli_root: Path, capsys) -> None:
    assert main(["--root", str(cli_root), "validate"]) == EXIT_OK
    assert "TOTAL" in capsys.readouterr().out


def test_translation_template(cli_root: Path, capsys) -> None:
    assert main(["--root", str(cli_root), "export-translation-template"]) == EXIT_OK
    assert "wrote" in capsys.readouterr().out
    assert (cli_root / "data" / "reports" / "translation-template-ar.csv").is_file()


def test_build_without_app_bundle(tmp_path: Path, capsys) -> None:
    root = create_project(tmp_path / "no-bundle")
    assert main(["--root", str(root), "import", "--all"]) == EXIT_OK
    assert main([
        "--root", str(root), "build-db", "--version", "0.2.0", "--no-app-bundle"
    ]) == EXIT_OK
    output = capsys.readouterr().out
    assert "status:         passed" in output
    assert not (root / "data" / "exports" / "autodoctor-app-0.2.0.sqlite").exists()


def test_import_requires_a_source(capsys, tmp_path: Path) -> None:
    root = create_project(tmp_path / "usage", with_upstream=False)
    assert main(["--root", str(root), "import"]) == 2
    assert "pass --source" in capsys.readouterr().out


def test_build_without_any_import_fails(tmp_path: Path, capsys) -> None:
    root = create_project(tmp_path / "empty")
    assert main(["--root", str(root), "build-db"]) == EXIT_FAILURE
    assert "no staged imports" in capsys.readouterr().out
