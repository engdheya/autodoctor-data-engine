"""Human readable reports.

Numbers in these reports are always queried from the built database or from the
staged artifacts - never estimated.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..config import Settings
from ..staging import available_bundles


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def import_report(settings: Settings) -> dict[str, Any]:
    sources = []
    for manifest in available_bundles(settings):
        stats = manifest.get("stats", {})
        sources.append(
            {
                "slug": manifest["slug"],
                "commit_sha": manifest["commit_sha"],
                "version_label": manifest.get("version_label"),
                "retrieved_at": manifest["retrieved_at"],
                "files": len(manifest.get("files", [])),
                "record_counts": manifest.get("record_counts", {}),
                "total_records": manifest.get("total_records", 0),
                "raw_records": stats.get("raw_records", 0),
                "rejected_records": stats.get("rejected_records", 0),
                "validation": stats.get("validation", {}),
                "warnings": stats.get("warnings", []),
                "content_hash": manifest["content_hash"],
            }
        )
    return {"generated_at": _now(), "sources": sources}


def database_report(settings: Settings, conn: sqlite3.Connection) -> dict[str, Any]:
    from ..utils.hashing import sha256_file

    def scalar(query: str, params: tuple = ()) -> int:
        row = conn.execute(query, params).fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    counts = {
        "dtc_codes": scalar("SELECT COUNT(*) FROM dtc_codes"),
        "dtc_codes_distinct": scalar("SELECT COUNT(DISTINCT code) FROM dtc_codes"),
        "definitions": scalar("SELECT COUNT(*) FROM dtc_definitions"),
        "definitions_verified": scalar(
            "SELECT COUNT(*) FROM dtc_definitions WHERE verification_status='verified'"),
        "definitions_source_reported": scalar(
            "SELECT COUNT(*) FROM dtc_definitions WHERE verification_status='source_reported'"),
        "definitions_conflicting": scalar(
            "SELECT COUNT(*) FROM dtc_definitions WHERE verification_status='conflicting'"),
        "definitions_unverified": scalar(
            "SELECT COUNT(*) FROM dtc_definitions WHERE verification_status='unverified'"),
        "causes": scalar("SELECT COUNT(*) FROM dtc_causes"),
        "symptoms": scalar("SELECT COUNT(*) FROM dtc_symptoms"),
        "tests": scalar("SELECT COUNT(*) FROM dtc_tests"),
        "repairs": scalar("SELECT COUNT(*) FROM dtc_repairs"),
        "related_codes": scalar("SELECT COUNT(*) FROM dtc_related_codes"),
        "components": scalar("SELECT COUNT(*) FROM dtc_components"),
        "pids": scalar("SELECT COUNT(*) FROM pids"),
        "vehicles": scalar("SELECT COUNT(*) FROM vehicles"),
        "vehicle_variants": scalar("SELECT COUNT(*) FROM vehicle_variants"),
        "manufacturers": scalar("SELECT COUNT(*) FROM manufacturers"),
        "ecus": scalar("SELECT COUNT(*) FROM ecus"),
        "claims": scalar("SELECT COUNT(*) FROM provenance_claims"),
        "source_records": scalar("SELECT COUNT(*) FROM source_records"),
        "source_files": scalar("SELECT COUNT(*) FROM source_files"),
        "conflicts": scalar("SELECT COUNT(*) FROM conflicts"),
        "conflicts_open": scalar(
            "SELECT COUNT(*) FROM conflicts WHERE status='needs_review'"),
        "duplicate_groups": scalar("SELECT COUNT(*) FROM duplicate_groups"),
        "validation_failures": scalar(
            "SELECT COUNT(*) FROM validation_results WHERE passed = 0"),
        "codes_with_arabic": scalar(
            "SELECT COUNT(DISTINCT dtc_code_id) FROM dtc_definitions WHERE language='ar'"),
        "codes_with_causes": scalar(
            "SELECT COUNT(DISTINCT dtc_code_id) FROM dtc_causes"),
        "codes_with_tests": scalar(
            "SELECT COUNT(DISTINCT dtc_code_id) FROM dtc_tests"),
        "codes_with_repairs": scalar(
            "SELECT COUNT(DISTINCT dtc_code_id) FROM dtc_repairs"),
    }

    coverage = {
        "generic_codes": scalar("SELECT COUNT(*) FROM dtc_codes WHERE context_type='generic'"),
        "manufacturer_codes": scalar(
            "SELECT COUNT(*) FROM dtc_codes WHERE context_type='manufacturer'"),
        "ecu_codes": scalar("SELECT COUNT(*) FROM dtc_codes WHERE context_type='ecu'"),
        "vehicle_codes": scalar(
            "SELECT COUNT(*) FROM dtc_codes WHERE context_type='vehicle_variant'"),
        "arabic_definitions": scalar("SELECT COUNT(*) FROM dtc_definitions WHERE language='ar'"),
        "german_definitions": scalar("SELECT COUNT(*) FROM dtc_definitions WHERE language='de'"),
        "english_definitions": scalar("SELECT COUNT(*) FROM dtc_definitions WHERE language='en'"),
    }

    sources = [
        dict(row)
        for row in conn.execute(
            """
            SELECT s.slug, s.name, s.repo_url, s.code_license, s.data_license,
                   s.share_alike, s.legal_review_status, s.lineage_group,
                   v.commit_sha, v.retrieved_at,
                   (SELECT COUNT(*) FROM provenance_claims p WHERE p.source_id = s.id) AS claims
            FROM data_sources s LEFT JOIN data_versions v ON v.source_id = s.id
            ORDER BY s.slug
            """
        )
    ]

    conflicts_by_type = {
        row[0]: int(row[1])
        for row in conn.execute(
            "SELECT conflict_type, COUNT(*) FROM conflicts GROUP BY 1 ORDER BY 2 DESC"
        )
    }
    duplicates_by_type = {
        row[0]: int(row[1])
        for row in conn.execute(
            "SELECT match_type, COUNT(*) FROM duplicate_groups GROUP BY 1 ORDER BY 2 DESC"
        )
    }
    versions = [
        dict(row)
        for row in conn.execute(
            "SELECT version, built_at, test_status, sha256 FROM db_versions ORDER BY id DESC LIMIT 5"
        )
    ]

    db_path = settings.database_path()
    return {
        "generated_at": _now(),
        "database": str(db_path),
        "database_bytes": db_path.stat().st_size if db_path.is_file() else 0,
        "database_sha256": sha256_file(db_path) if db_path.is_file() else None,
        "counts": counts,
        "coverage": coverage,
        "sources": sources,
        "conflicts_by_type": conflicts_by_type,
        "duplicates_by_type": duplicates_by_type,
        "releases": versions,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# AutoDoctor data report", "", f"Generated: {report['generated_at']}", ""]
    lines.append(f"Database: `{report['database']}` ({report['database_bytes']:,} bytes)")
    if report.get("database_sha256"):
        lines.append(f"SHA-256: `{report['database_sha256']}`")
    lines.append("")

    lines.append("## Database contents")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | ---: |")
    for key, value in report["counts"].items():
        lines.append(f"| {key.replace('_', ' ')} | {value:,} |")
    lines.append("")

    lines.append("## Coverage by context")
    lines.append("")
    lines.append("| Dimension | Value |")
    lines.append("| --- | ---: |")
    for key, value in report["coverage"].items():
        lines.append(f"| {key.replace('_', ' ')} | {value:,} |")
    lines.append("")

    lines.append("## Sources")
    lines.append("")
    lines.append("| Source | Commit | Data licence | Share-alike | Legal review | Claims |")
    lines.append("| --- | --- | --- | --- | --- | ---: |")
    for source in report["sources"]:
        lines.append(
            f"| {source['slug']} | `{(source['commit_sha'] or '')[:12]}` | "
            f"{source['data_license'] or '?'} | {bool(source['share_alike'])} | "
            f"{source['legal_review_status']} | {source['claims']:,} |"
        )
    lines.append("")

    if report["conflicts_by_type"]:
        lines.append("## Open conflicts by type")
        lines.append("")
        for key, value in report["conflicts_by_type"].items():
            lines.append(f"- {key}: {value:,}")
        lines.append("")

    if report["duplicates_by_type"]:
        lines.append("## Duplicate groups by type")
        lines.append("")
        for key, value in report["duplicates_by_type"].items():
            lines.append(f"- {key}: {value:,}")
        lines.append("")

    if report["releases"]:
        lines.append("## Releases")
        lines.append("")
        lines.append("| Version | Built | Status | SHA-256 |")
        lines.append("| --- | --- | --- | --- |")
        for release in report["releases"]:
            lines.append(
                f"| {release['version']} | {release['built_at']} | {release['test_status']} | "
                f"`{(release['sha256'] or '')[:16]}` |"
            )
        lines.append("")
    return "\n".join(lines)


def write_report(settings: Settings, report: dict[str, Any], *, prefix: str = "data-report") -> tuple[Path, Path]:
    settings.paths.reports.mkdir(parents=True, exist_ok=True)
    json_path = settings.paths.reports / f"{prefix}.json"
    md_path = settings.paths.reports / f"{prefix}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def render_import_report(report: dict[str, Any]) -> str:
    lines = ["# Import report", "", f"Generated: {report['generated_at']}", ""]
    if not report["sources"]:
        lines.append("_No source has been imported yet._")
        return "\n".join(lines)
    lines.append("| Source | Commit | Raw records | Normalized | Rejected | Files |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: |")
    for source in report["sources"]:
        lines.append(
            f"| {source['slug']} | `{source['commit_sha'][:12]}` | {source['raw_records']:,} | "
            f"{source['total_records']:,} | {source['rejected_records']:,} | {source['files']:,} |"
        )
    lines.append("")
    for source in report["sources"]:
        lines.append(f"## {source['slug']}")
        lines.append("")
        lines.append(f"- repository commit: `{source['commit_sha']}` ({source['version_label']})")
        lines.append(f"- retrieved at: {source['retrieved_at']}")
        lines.append(f"- content hash: `{source['content_hash']}`")
        lines.append(f"- record types: {json.dumps(source['record_counts'], ensure_ascii=False)}")
        validation = source.get("validation") or {}
        if validation:
            lines.append(
                f"- validation: {validation.get('passed', 0)} checks passed, "
                f"{validation.get('failed', 0)} failed "
                f"({validation.get('errors', 0)} errors, {validation.get('warnings', 0)} warnings)"
            )
        if source.get("warnings"):
            lines.append("- warnings:")
            lines.extend(f"  - {w}" for w in source["warnings"])
        lines.append("")
    return "\n".join(lines)
