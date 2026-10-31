"""Format readers: YAML, JSON, SQLite, CSV and the plain "CODE - text" lists."""

from __future__ import annotations

import json
import sqlite3

import pytest

from autodoctor_data_engine.parsers import (
    load_json,
    load_yaml,
    parse_code_list,
    read_csv_rows,
    read_sqlite,
    read_text_lines,
)
from autodoctor_data_engine.parsers.json_loader import JsonParseError
from autodoctor_data_engine.parsers.yaml_loader import YamlParseError


def test_load_yaml_list(tmp_path) -> None:
    path = tmp_path / "codes.yaml"
    path.write_text("- code: P0301\n  title: Misfire\n- code: P0420\n  title: Catalyst\n",
                    encoding="utf-8")
    data = load_yaml(path)
    assert [row["code"] for row in data] == ["P0301", "P0420"]


def test_load_yaml_reports_the_offending_file(tmp_path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text("code: [unclosed\n", encoding="utf-8")
    with pytest.raises(YamlParseError) as excinfo:
        load_yaml(path)
    assert "broken.yaml" in str(excinfo.value)


def test_load_json(tmp_path) -> None:
    path = tmp_path / "signalset.json"
    path.write_text(json.dumps({"ecu": [{"hdr": "7E0"}], "commands": []}), encoding="utf-8")
    assert load_json(path)["ecu"][0]["hdr"] == "7E0"


def test_load_json_error_mentions_the_file(tmp_path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(JsonParseError):
        load_json(path)


def test_read_sqlite_is_read_only(tmp_path) -> None:
    path = tmp_path / "source.db"
    conn = sqlite3.connect(path)
    conn.executescript("CREATE TABLE t (a TEXT); INSERT INTO t VALUES ('x');")
    conn.commit()
    conn.close()

    rows = list(read_sqlite(path, "SELECT a FROM t"))
    assert rows == [{"a": "x"}]

    with pytest.raises(sqlite3.OperationalError):
        list(read_sqlite(path, "DELETE FROM t"))


def test_read_csv_rows(tmp_path) -> None:
    path = tmp_path / "codes.csv"
    path.write_text("code,description\nP0301,Cylinder 1 misfire\n", encoding="utf-8")
    rows = list(read_csv_rows(path))
    assert rows[0]["code"] == "P0301"
    assert rows[0]["description"] == "Cylinder 1 misfire"


def test_read_csv_semicolon_delimiter(tmp_path) -> None:
    path = tmp_path / "codes.csv"
    path.write_text("code;description\nP0301;Misfire\n", encoding="utf-8")
    rows = list(read_csv_rows(path))
    assert rows[0]["description"] == "Misfire"


def test_parse_code_list_handles_separators(tmp_path) -> None:
    path = tmp_path / "p_codes.txt"
    path.write_text(
        "P0301 - Cylinder 1 Misfire Detected\n"
        "P0420 – Catalyst efficiency\n"
        "P0100: Mass air flow circuit\n"
        "not-a-code line without separator\n\n",
        encoding="utf-8",
    )
    parsed = list(parse_code_list(path))
    assert parsed[0] == (1, "P0301", "Cylinder 1 Misfire Detected")
    assert parsed[1][2] == "Catalyst efficiency"
    assert parsed[2][2] == "Mass air flow circuit"
    assert len(parsed) == 3


def test_read_text_lines_skips_blank_lines(tmp_path) -> None:
    path = tmp_path / "list.txt"
    path.write_text("a\n\n b \n", encoding="utf-8")
    assert list(read_text_lines(path)) == ["a", " b "]
