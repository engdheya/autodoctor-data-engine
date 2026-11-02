#!/usr/bin/env python3
"""Assemble a downloadable delivery folder from a built export.

    python scripts/package_delivery.py --version 0.9.0

Reads `data/exports/` and `data/reports/`, writes `deliveries/<version>/` containing the
compressed artifacts (SQLite compresses ~5x, which keeps the package inside git's limits),
the reports, the conflict pack, the Flutter harness and a SHA256SUMS manifest. Running it
twice on the same inputs produces the same hashes.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REPORTS = (
    "coverage.md",
    "coverage.json",
    "completeness.md",
    "completeness.csv",
    "completeness.json",
    "conflict-triage.md",
    "conflict-triage.json",
    "licences.md",
    "licences.json",
)
COMPRESS = {".sqlite", ".csv", ".json"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def gzip_copy(source: Path, target: Path) -> None:
    with source.open("rb") as raw, gzip.GzipFile(
        filename="", mode="wb", fileobj=target.open("wb"), mtime=0, compresslevel=9
    ) as gz:
        shutil.copyfileobj(raw, gz, 1 << 20)


def put(source: Path, target: Path, compress: bool) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if compress and source.suffix in COMPRESS:
        target = target.with_suffix(target.suffix + ".gz")
        gzip_copy(source, target)
    else:
        shutil.copy2(source, target)
    return target


def zip_dir(source: Path, target: Path) -> None:
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file() and not any(p in path.parts for p in ("build", ".dart_tool")):
                archive.write(path, path.relative_to(source.parent))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="0.9.0")
    args = parser.parse_args()

    exports = ROOT / "data" / "exports"
    reports = ROOT / "data" / "reports"
    out = ROOT / "deliveries" / args.version
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    produced: list[Path] = []
    for name in (
        f"autodoctor-{args.version}-public.sqlite",
        f"autodoctor-app-{args.version}-public.sqlite",
        f"autodoctor-{args.version}-public.manifest.json",
    ):
        produced.append(put(exports / name, out / name, compress=True))

    for name in REPORTS:
        produced.append(put(reports / name, out / "reports" / name, compress=True))

    produced.append(put(ROOT / "data" / "reviews" / "batches" / "critical-001.yaml",
                        out / "packs" / "critical-001.yaml", compress=False))
    zip_dir(ROOT / "flutter_harness", out / f"flutter_harness-{args.version}.zip")
    produced.append(out / f"flutter_harness-{args.version}.zip")
    shutil.copy2(ROOT / "scripts" / "verify_delivery.py", out / "verify_delivery.py")
    produced.append(out / "verify_delivery.py")

    sums = []
    for path in sorted(produced):
        sums.append(f"{sha256(path)}  {path.relative_to(out).as_posix()}")
    (out / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")

    manifest = json.loads((exports / f"autodoctor-{args.version}-public.manifest.json").read_text())
    print(f"packaged {len(produced)} files into {out}")
    print(f"  database  {manifest['database_bytes']:,} B  sha256 {manifest['database_sha256']}")
    print(f"  bundle    {manifest['app_bundle']['bytes']:,} B  sha256 {manifest['app_bundle']['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
