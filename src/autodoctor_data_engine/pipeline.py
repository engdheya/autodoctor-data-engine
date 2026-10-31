"""Extraction pipeline: inspect -> extract -> raw archive -> normalize -> validate.

Everything is streamed to disk so that a source with 60k records does not need to
fit in memory. The raw archive is written *before* normalization and is never
modified afterwards, which is what allows a rebuild to be audited years later.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import Settings
from .connectors import ConnectorError, SourceInspection, build_connector
from .normalizers.text import clean_text
from .staging import raw_dir, staging_dir
from .utils.hashing import sha256_file, sha256_json
from .validators.rules import ValidationIssue, blockable_errors, summarize, validate_record


class ImportRejected(RuntimeError):
    def __init__(self, slug: str, rejected: int, samples: list[dict[str, Any]]):
        super().__init__(
            f"{slug}: import rejected, {rejected} record(s) failed blocking validation rules"
        )
        self.slug = slug
        self.rejected = rejected
        self.samples = samples


@dataclass
class ImportResult:
    slug: str
    commit_sha: str
    records_raw: int
    records_normalized: int
    record_counts: dict[str, int]
    files: int
    validation: dict[str, Any]
    rejected: int
    rejected_samples: list[dict[str, Any]]
    warnings: list[str]
    manifest_path: Path
    duration_seconds: float
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.slug,
            "commit_sha": self.commit_sha,
            "records_raw": self.records_raw,
            "records_normalized": self.records_normalized,
            "record_counts": self.record_counts,
            "files": self.files,
            "validation": self.validation,
            "rejected": self.rejected,
            "rejected_samples": self.rejected_samples,
            "warnings": self.warnings,
            "manifest": str(self.manifest_path),
            "duration_seconds": round(self.duration_seconds, 2),
            "content_hash": self.content_hash,
        }


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class _StreamWriter:
    """Append JSONL rows without keeping them in memory."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._fh = open(path, "w", encoding="utf-8")  # noqa: SIM115
        self.count = 0

    def write(self, row: dict[str, Any]) -> None:
        self._fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
        self._fh.write("\n")
        self.count += 1

    def close(self) -> None:
        self._fh.close()

    def __enter__(self) -> _StreamWriter:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def inspect_sources(settings: Settings, slugs: list[str] | None = None) -> list[SourceInspection]:
    inspections: list[SourceInspection] = []
    for source in settings.enabled_sources():
        if slugs and source.slug not in slugs:
            continue
        connector = build_connector(settings, source.slug)
        try:
            inspections.append(connector.inspect())
        except ConnectorError as exc:
            inspections.append(
                SourceInspection(
                    slug=source.slug,
                    name=source.name,
                    repo_url=source.repo_url,
                    local_path=str(source.local_path),
                    present=False,
                    commit_sha=None,
                    describe=None,
                    dirty=False,
                    file_count=0,
                    total_bytes=0,
                    layout={},
                    licence=connector.licence_dict(),
                    notes=source.notes,
                    warnings=[str(exc)],
                )
            )
    return inspections


def write_inspection_report(settings: Settings, inspections: list[SourceInspection]) -> Path:
    settings.paths.reports.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": _now(),
        "sources": [i.to_dict() for i in inspections],
    }
    json_path = settings.paths.reports / "source-inspection.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["# Source inspection", "", f"Generated: {payload['generated_at']}", ""]
    for inspection in inspections:
        lines.append(f"## {inspection.name} (`{inspection.slug}`)")
        lines.append("")
        lines.append(f"- repository: {inspection.repo_url}")
        lines.append(f"- local path: `{inspection.local_path}`")
        lines.append(f"- present: {inspection.present}")
        lines.append(f"- commit: `{inspection.commit_sha}` ({inspection.describe or 'no tag'})")
        lines.append(f"- dirty working tree: {inspection.dirty}")
        lines.append(f"- files: {inspection.file_count}, bytes: {inspection.total_bytes}")
        lines.append(
            f"- licence: code={inspection.licence.get('code')}, "
            f"data={inspection.licence.get('data')}, "
            f"review={inspection.licence.get('legal_review')}"
        )
        if inspection.layout:
            lines.append("- layout:")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(inspection.layout, indent=2, ensure_ascii=False))
            lines.append("```")
        if inspection.warnings:
            lines.append("- warnings:")
            lines.extend(f"  - {w}" for w in inspection.warnings)
        lines.append("")
    md_path = settings.paths.reports / "source-inspection.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


def import_source(
    settings: Settings,
    slug: str,
    *,
    fail_on_error: bool = False,
    limit: int | None = None,
) -> ImportResult:
    started = time.time()
    connector = build_connector(settings, slug)
    version = connector.version_info()
    commit = version.commit or "uncommitted"
    retrieved_at = _now()
    warnings = list(version.warnings)

    raw_target = raw_dir(settings, slug, commit)
    stage_target = staging_dir(settings, slug, commit)
    raw_target.mkdir(parents=True, exist_ok=True)
    stage_target.mkdir(parents=True, exist_ok=True)

    file_stats: dict[str, dict[str, Any]] = {}
    record_counts: dict[str, int] = {}
    validation_counts = {"total": 0, "passed": 0, "failed": 0, "errors": 0, "warnings": 0}
    rejected = 0
    rejected_samples: list[dict[str, Any]] = []
    raw_count = 0
    normalized_count = 0
    raw_writers: dict[str, _StreamWriter] = {}
    normalized_writer = _StreamWriter(stage_target / "normalized.jsonl")
    validation_writer = _StreamWriter(stage_target / "validation.jsonl")

    for raw in connector.extract():
        if limit and raw_count >= limit:
            break
        raw_count += 1
        writer = raw_writers.get(raw.record_type)
        if writer is None:
            writer = _StreamWriter(raw_target / f"{raw.record_type}.jsonl")
            raw_writers[raw.record_type] = writer
        writer.write(
            {
                "source_record_id": raw.source_record_id,
                "file_path": raw.file_path,
                "record_type": raw.record_type,
                "raw_hash": raw.payload_hash(),
                "payload": raw.payload,
                "extra": raw.extra,
            }
        )
        entry = file_stats.setdefault(
            raw.file_path, {"path": raw.file_path, "record_types": set(), "records": 0}
        )
        entry["record_types"].add(raw.record_type)
        entry["records"] += 1

        provenance_base = connector.provenance_base(raw, commit)
        try:
            normalized = list(connector.normalize(raw, provenance_base))
        except Exception as exc:  # noqa: BLE001 - one bad record must not abort the source
            rejected += 1
            validation_counts["errors"] += 1
            validation_counts["failed"] += 1
            validation_counts["total"] += 1
            if len(rejected_samples) < 25:
                rejected_samples.append(
                    {
                        "record": raw.source_record_id,
                        "rules": ["N001_normalization"],
                        "messages": [str(exc)[:300]],
                    }
                )
            continue
        for record in normalized:
            normalized_count += 1
            record_counts[record.record_type] = record_counts.get(record.record_type, 0) + 1
            try:
                issues: list[ValidationIssue] = validate_record(record, settings.rules)
            except Exception as exc:  # noqa: BLE001
                issues = [
                    ValidationIssue(
                        rule_id="N002_validation_crash",
                        severity="error",
                        passed=False,
                        message=str(exc)[:300],
                        entity_type=record.record_type,
                        entity_key=record.provenance.source_record_id,
                    )
                ]
            for issue in issues:
                validation_writer.write(issue.to_dict())
            summary = summarize(issues)
            for key in validation_counts:
                validation_counts[key] += summary[key]
            blocking = blockable_errors(issues)
            if blocking:
                rejected += 1
                if len(rejected_samples) < 25:
                    rejected_samples.append(
                        {
                            "record": record.provenance.source_record_id,
                            "rules": sorted({i.rule_id for i in blocking}),
                            "messages": [i.message for i in blocking][:3],
                        }
                    )
                continue
            normalized_writer.write(record.model_dump(mode="json"))

    normalized_writer.close()
    validation_writer.close()
    for writer in raw_writers.values():
        writer.close()
    raw_relative = str(raw_target.relative_to(settings.root))

    # file hashes (only files that actually produced records)
    for path, entry in file_stats.items():
        absolute = connector.root / path
        entry["sha256"] = sha256_file(absolute) if absolute.is_file() else ""
        entry["size_bytes"] = absolute.stat().st_size if absolute.is_file() else 0
        entry["record_type"] = (
            next(iter(entry["record_types"])) if len(entry["record_types"]) == 1 else None
        )
        entry["record_count"] = entry["records"]
        entry.pop("record_types")
        entry.pop("records")

    content_hash = sha256_json(
        {"commit": commit, "files": sorted((p, e["sha256"]) for p, e in file_stats.items())}
    )

    manifest = {
        "slug": slug,
        "commit_sha": commit,
        "version_label": version.label or "HEAD",
        "retrieved_at": retrieved_at,
        "content_hash": content_hash,
        "raw_archive": raw_relative,
        "files": [file_stats[p] for p in sorted(file_stats)],
        "record_counts": record_counts,
        "total_records": normalized_count,
        "stats": {
            "raw_records": raw_count,
            "normalized_records": normalized_count,
            "rejected_records": rejected,
            "warnings": warnings,
            "duration_seconds": round(time.time() - started, 2),
            "validation": validation_counts,
            **({"repos": version.extra["repo_commits"]} if version.extra.get("repo_commits") else {}),
        },
    }
    manifest_path = stage_target / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    duration = time.time() - started
    result = ImportResult(
        slug=slug,
        commit_sha=commit,
        records_raw=raw_count,
        records_normalized=normalized_count,
        record_counts=record_counts,
        files=len(file_stats),
        validation=validation_counts,
        rejected=rejected,
        rejected_samples=rejected_samples,
        warnings=warnings,
        manifest_path=manifest_path,
        duration_seconds=duration,
        content_hash=content_hash,
    )
    if fail_on_error and rejected:
        raise ImportRejected(slug, rejected, rejected_samples)
    return result


def validate_staged(settings: Settings, slugs: list[str] | None = None) -> dict[str, Any]:
    """Aggregate the validation artifacts written during import."""
    from .staging import available_bundles

    results: dict[str, Any] = {"sources": {}, "totals": {}}
    totals = {"records": 0, "rejected": 0, "errors": 0, "warnings": 0}
    for manifest in available_bundles(settings, slugs):
        stats = manifest.get("stats", {})
        validation = stats.get("validation", {})
        results["sources"][manifest["slug"]] = {
            "commit_sha": manifest["commit_sha"],
            "records": manifest.get("total_records", 0),
            "rejected": stats.get("rejected_records", 0),
            **validation,
        }
        totals["records"] += manifest.get("total_records", 0)
        totals["rejected"] += stats.get("rejected_records", 0)
        totals["errors"] += validation.get("errors", 0)
        totals["warnings"] += validation.get("warnings", 0)
    results["totals"] = totals
    return results


def fetch_sources(settings: Settings, slugs: list[str] | None = None, *, limit: int = 5) -> dict[str, str]:
    """Shallow-clone enabled sources into the vendor directory (best effort)."""
    import subprocess

    settings.paths.upstream.mkdir(parents=True, exist_ok=True)
    outcome: dict[str, str] = {}
    for source in settings.enabled_sources():
        if slugs and source.slug not in slugs:
            continue
        target = source.local_path
        if target.exists():
            outcome[source.slug] = "already present"
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.slug == "obdb":
            # the org is a collection of repositories; clone the most useful subset
            names = _obdb_repo_names(limit)
            for name in names:
                sub = target / name
                if sub.exists():
                    continue
                sub.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    ["git", "clone", "--depth", "1",
                     f"https://github.com/OBDb/{name}.git", str(sub)],
                    check=False, capture_output=True, timeout=600,
                )
            outcome[source.slug] = f"cloned {len(names)} vehicle repositories"
            continue
        result = subprocess.run(
            ["git", "clone", "--depth", "1", source.repo_url, str(target)],
            check=False, capture_output=True, text=True, timeout=1800,
        )
        outcome[source.slug] = "cloned" if result.returncode == 0 else f"failed: {result.stderr.strip()[:200]}"
    return outcome


def _obdb_repo_names(limit: int) -> list[str]:
    """Ask the GitHub API for a few OBDb vehicle repositories."""
    import urllib.request

    url = "https://api.github.com/orgs/OBDb/repos?per_page=100&sort=updated"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
            data = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return ["Toyota-Camry"]
    names = [row["name"] for row in data if not row["name"].startswith(".")]
    return names[:limit]


def read_manifest(manifest_path: Path) -> dict[str, Any]:
    return json.loads(Path(manifest_path).read_text(encoding="utf-8"))


def _clean(value: Any) -> Any:
    return clean_text(value) if isinstance(value, str) else value


__all__ = [
    "ImportResult",
    "ImportRejected",
    "inspect_sources",
    "write_inspection_report",
    "import_source",
    "validate_staged",
    "fetch_sources",
    "read_manifest",
]
