"""CSV / plain-text readers.

Two shapes appear in practice:
  * real CSV files with a header row
  * "CODE - description" lists (the raw text files shipped by Wal33D)

Both are handled here so connectors stay declarative.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

_SPLIT = re.compile(r"\s*[-–—:]\s+|\t+")


def read_text_lines(path: str | Path) -> Iterator[str]:
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.strip():
                yield line


def read_csv_rows(path: str | Path) -> Iterator[dict[str, Any]]:
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        yield from csv.DictReader(fh, dialect=dialect)


def parse_code_list(path: str | Path) -> Iterator[tuple[int, str, str]]:
    """Yield (line_no, code, description) from a `CODE - description` text file."""
    for line_no, line in enumerate(read_text_lines(path), start=1):
        parts = _SPLIT.split(line.strip(), maxsplit=1)
        if len(parts) != 2:
            continue
        code, description = parts[0].strip(), parts[1].strip()
        if not code or not description:
            continue
        yield line_no, code, description
