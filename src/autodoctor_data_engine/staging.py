"""Staging layer: the hand-off between extraction and merging.

Layout::

    data/staging/<slug>/<commit>/manifest.json     files, hashes, counts
    data/staging/<slug>/<commit>/normalized.jsonl  validated normalized records
    data/raw/<slug>/<commit>/<record_type>.jsonl   verbatim upstream records

The raw archive is the immutable copy: normalization never rewrites it. The
staging archive can always be regenerated from raw + code, which is what makes an
upgrade reproducible.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Settings
from .models import NormalizedRecord, parse_record
from .utils.jsonl import read_jsonl, write_jsonl


@dataclass
class SourceBundle:
    slug: str
    commit_sha: str
    retrieved_at: str
    content_hash: str
    records: list[NormalizedRecord] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)
    version_label: str | None = None
    raw_archive: str | None = None
    stats: dict[str, Any] = field(default_factory=dict)

    def records_of_type(self, record_type: str) -> list[NormalizedRecord]:
        return [r for r in self.records if r.record_type == record_type]

    def to_manifest(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for record in self.records:
            counts[record.record_type] = counts.get(record.record_type, 0) + 1
        return {
            "slug": self.slug,
            "commit_sha": self.commit_sha,
            "version_label": self.version_label,
            "retrieved_at": self.retrieved_at,
            "content_hash": self.content_hash,
            "raw_archive": self.raw_archive,
            "files": self.files,
            "record_counts": counts,
            "total_records": len(self.records),
            "stats": self.stats,
        }


def staging_dir(settings: Settings, slug: str, commit_sha: str) -> Path:
    return settings.paths.staging / slug / commit_sha


def raw_dir(settings: Settings, slug: str, commit_sha: str) -> Path:
    return settings.paths.raw / slug / commit_sha


def write_bundle(settings: Settings, bundle: SourceBundle) -> Path:
    directory = staging_dir(settings, bundle.slug, bundle.commit_sha)
    directory.mkdir(parents=True, exist_ok=True)
    write_jsonl(directory / "normalized.jsonl", (r.model_dump(mode="json") for r in bundle.records))
    manifest_path = directory / "manifest.json"
    manifest_path.write_text(
        json.dumps(bundle.to_manifest(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest_path


def available_bundles(settings: Settings, slugs: list[str] | None = None) -> list[dict[str, Any]]:
    """Return manifests of every staged import, newest commit first per slug."""
    manifests: list[dict[str, Any]] = []
    for slug_dir in sorted(settings.paths.staging.glob("*")):
        if not slug_dir.is_dir():
            continue
        if slugs and slug_dir.name not in slugs:
            continue
        for manifest in sorted(slug_dir.glob("*/manifest.json")):
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            data["_manifest_path"] = str(manifest)
            manifests.append(data)
    # keep only the latest commit per slug
    latest: dict[str, dict[str, Any]] = {}
    for manifest in manifests:
        current = latest.get(manifest["slug"])
        if current is None or manifest["retrieved_at"] > current["retrieved_at"]:
            latest[manifest["slug"]] = manifest
    return list(latest.values())


def load_bundle(manifest: dict[str, Any], settings: Settings) -> SourceBundle:
    slug = manifest["slug"]
    commit = manifest["commit_sha"]
    directory = staging_dir(settings, slug, commit)
    records = [parse_record(row) for row in read_jsonl(directory / "normalized.jsonl")]
    return SourceBundle(
        slug=slug,
        commit_sha=commit,
        retrieved_at=manifest["retrieved_at"],
        content_hash=manifest["content_hash"],
        records=records,
        files=manifest.get("files", []),
        version_label=manifest.get("version_label"),
        raw_archive=manifest.get("raw_archive"),
        stats=manifest.get("stats", {}),
    )


def load_all_bundles(settings: Settings, slugs: list[str] | None = None) -> list[SourceBundle]:
    return [load_bundle(m, settings) for m in available_bundles(settings, slugs)]
