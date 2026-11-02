#!/usr/bin/env python3
"""Verify a delivered AutoDoctor package against its SHA256SUMS file.

Usage:
    python verify_delivery.py            # checks the folder this file sits in
    python verify_delivery.py /path/dir  # or an explicit folder

Exit code 0 only when every listed file exists and matches its hash byte for byte.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

BLOCK = 1 << 20


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(BLOCK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    root = Path(argv[0]) if argv else Path(__file__).resolve().parent
    sums = root / "SHA256SUMS"
    if not sums.is_file():
        print(f"no SHA256SUMS in {root}", file=sys.stderr)
        return 2

    failures = 0
    checked = 0
    for line in sums.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        expected, _, name = line.partition("  ")
        if not name:
            print(f"malformed line: {line}", file=sys.stderr)
            failures += 1
            continue
        target = root / name
        if not target.is_file():
            print(f"MISSING  {name}")
            failures += 1
            continue
        actual = sha256(target)
        checked += 1
        if actual == expected:
            print(f"OK       {name}  {actual}")
        else:
            print(f"MISMATCH {name}\n  expected {expected}\n  actual   {actual}")
            failures += 1

    print(f"\n{checked} file(s) hashed, {failures} problem(s)")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
