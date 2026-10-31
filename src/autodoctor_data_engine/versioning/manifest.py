"""Release manifests.

A manifest is the contract between the data engine and whoever consumes a release:
it records the exact upstream commits, the licence status of every source, the
row counts, the validation outcome and the SHA-256 of the shipped file.

Versioning follows semver with an explicit meaning:
  major - schema change or a removal that breaks clients
  minor - new codes / new sources / new content dimensions
  patch - corrections, translations, licence metadata
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..utils.hashing import sha256_file

SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


@dataclass
class Manifest:
    version: str
    built_at: str
    engine_version: str
    engine_commit: str | None
    schema_version: str
    database_file: str
    database_sha256: str
    database_bytes: int
    sources: list[dict[str, Any]] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)
    checks: list[dict[str, Any]] = field(default_factory=list)
    test_status: str = "pending"
    notes: str | None = None
    app_bundle: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def bump_version(version: str, part: str = "patch") -> str:
    match = SEMVER.match(version)
    if not match:
        raise ValueError(f"not a semver version: {version!r}")
    major, minor, patch = (int(g) for g in match.groups())
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"unknown version part: {part!r}")


def next_version(exports_dir: Path, part: str = "patch", initial: str = "0.1.0") -> str:
    versions = []
    for manifest in exports_dir.glob("*.manifest.json"):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        version = data.get("version")
        if version and SEMVER.match(version):
            versions.append(version)
    if not versions:
        return initial
    latest = max(versions, key=lambda v: tuple(int(p) for p in v.split(".")))
    return bump_version(latest, part)


def build_manifest(
    *,
    version: str,
    engine_version: str,
    engine_commit: str | None,
    database_path: Path,
    sources: list[dict[str, Any]],
    counts: dict[str, int],
    validation: dict[str, Any],
    checks: list[dict[str, Any]],
    test_status: str,
    schema_version: str = "1",
    notes: str | None = None,
    app_bundle: dict[str, Any] | None = None,
) -> Manifest:
    return Manifest(
        version=version,
        built_at=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        engine_version=engine_version,
        engine_commit=engine_commit,
        schema_version=schema_version,
        database_file=database_path.name,
        database_sha256=sha256_file(database_path),
        database_bytes=database_path.stat().st_size,
        sources=sources,
        counts=counts,
        validation=validation,
        checks=checks,
        test_status=test_status,
        notes=notes,
        app_bundle=app_bundle,
    )


def write_manifest(manifest: Manifest, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return path


def read_manifest(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def latest_manifest(exports_dir: Path) -> dict[str, Any] | None:
    manifests = sorted(exports_dir.glob("*.manifest.json"))
    if not manifests:
        return None
    latest = max(
        manifests,
        key=lambda p: tuple(
            int(x) for x in json.loads(p.read_text(encoding="utf-8"))["version"].split(".")
        ),
    )
    return read_manifest(latest)
