"""Build the unified SQLite database and publish a release.

The build is deliberately fail-closed:

1. the working database is always built (so failures can be inspected),
2. release gates are evaluated against the *built file* (FKs, provenance,
   uniqueness, licence review status),
3. the export + manifest are only produced when every blocking gate passes.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .. import __version__ as engine_version
from ..config import DEFAULT_SOURCE_SET, SOURCE_SETS, Settings
from ..conflict_resolution.detector import Conflict, detect_conflicts
from ..deduplication.detector import DuplicateGroup, detect_duplicates
from ..merger.loader import MergeLoader
from ..models import NormalizedDtc, NormalizedRecord
from ..reviews import ReviewStore
from ..staging import SourceBundle, available_bundles, load_all_bundles
from ..translations import TranslationEntry, load_translations
from ..utils.gitinfo import commit_sha
from ..utils.hashing import sha256_file, sha256_text
from ..validators.database_rules import DatabaseCheck, failed_blocking, run_database_checks
from ..validators.rules import ValidationIssue, blockable_errors, summarize, validate_record
from ..versioning.manifest import build_manifest, next_version, write_manifest
from .app_export import LicenceError, build_app_bundle
from .connection import create_database, optimise

SCHEMA_VERSION = "3"


class BuildError(RuntimeError):
    pass


@dataclass
class BuildResult:
    version: str
    database_path: Path
    export_path: Path | None
    manifest_path: Path | None
    stats: dict[str, Any]
    counts: dict[str, int]
    validation: dict[str, Any]
    checks: list[DatabaseCheck]
    conflicts: list[Conflict]
    duplicate_groups: list[DuplicateGroup]
    rejected: list[dict[str, Any]]
    warnings: list[str]
    test_status: str
    source_set: str = DEFAULT_SOURCE_SET
    sources_excluded: list[dict[str, str]] = field(default_factory=list)
    review_stats: dict[str, int] = field(default_factory=dict)
    sources: list[dict[str, Any]] = field(default_factory=list)
    translation_entries: int = 0
    app_bundle_path: Path | None = None
    app_bundle_bytes: int = 0

    @property
    def published(self) -> bool:
        return self.test_status == "passed" and self.export_path is not None

    def summary(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "source_set": self.source_set,
            "sources_excluded": self.sources_excluded,
            "review_stats": self.review_stats,
            "database": str(self.database_path),
            "export": str(self.export_path) if self.export_path else None,
            "manifest": str(self.manifest_path) if self.manifest_path else None,
            "app_bundle": str(self.app_bundle_path) if self.app_bundle_path else None,
            "app_bundle_bytes": self.app_bundle_bytes,
            "test_status": self.test_status,
            "counts": self.counts,
            "validation": self.validation,
            "checks": [c.__dict__ for c in self.checks],
            "rejected_records": len(self.rejected),
            "conflicts": len(self.conflicts),
            "duplicate_groups": len(self.duplicate_groups),
            "translations": self.translation_entries,
            "warnings": self.warnings,
        }


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _record_key(record: NormalizedRecord) -> str:
    return f"{record.provenance.source_slug}:{record.provenance.source_record_id}"


def _source_payload(settings: Settings, bundle: SourceBundle) -> dict[str, Any]:
    source = settings.source(bundle.slug)
    return {
        "slug": bundle.slug,
        "name": source.name,
        "repo_url": source.repo_url,
        "commit_sha": bundle.commit_sha,
        "version_label": bundle.version_label,
        "content_hash": bundle.content_hash,
        "retrieved_at": bundle.retrieved_at,
        "records": len(bundle.records),
        "code_license": source.licence.code,
        "data_license": source.licence.data,
        "legal_review": source.licence.legal_review,
        "share_alike": source.licence.share_alike,
        "redistribution_allowed": source.licence.redistribution_allowed,
    }


def build_database(
    settings: Settings,
    *,
    version: str | None = None,
    part: str = "patch",
    slugs: list[str] | None = None,
    include_raw: bool = False,
    include_unreviewed_translations: bool = False,
    strict: bool = False,
    export: bool = True,
    app_bundle: bool = True,
    source_set: str = DEFAULT_SOURCE_SET,
    reviews: ReviewStore | None = None,
    allow_critical_conflicts: str | None = None,
    override_reviewer: str | None = None,
) -> BuildResult:
    settings.paths.ensure()
    if source_set not in SOURCE_SETS:
        raise BuildError(
            f"unknown source set {source_set!r}; expected one of {', '.join(SOURCE_SETS)}"
        )
    allowed_slugs, source_set_report = settings.resolve_source_set(source_set, slugs)
    excluded_sources = source_set_report["excluded"]
    bundles = load_all_bundles(settings, allowed_slugs)
    if not bundles:
        raise BuildError(
            "no staged imports found under "
            f"{settings.paths.staging}; run `autodoctor import --source <slug>` first"
        )

    warnings: list[str] = []
    if allow_critical_conflicts:
        warnings.append(
            "D012 overridden: unreviewed critical conflicts are being published "
            f"deliberately (reason: {allow_critical_conflicts}; "
            f"reviewer: {override_reviewer or 'unknown'})"
        )
    for entry in excluded_sources:
        warnings.append(
            f"source set {source_set}: {entry['slug']} excluded ({entry['reason']}, "
            f"{entry['data_license']})"
        )
    rule_counts: dict[str, dict[str, Any]] = {}
    failures: list[ValidationIssue] = []
    rejected: list[dict[str, Any]] = []
    accepted: list[NormalizedRecord] = []
    totals = {"total": 0, "passed": 0, "failed": 0, "errors": 0, "warnings": 0}

    for bundle in bundles:
        for record in bundle.records:
            issues = validate_record(record, settings.rules)
            summary = summarize(issues)
            for key, value in summary.items():
                totals[key] += value
            for issue in issues:
                entry = rule_counts.setdefault(
                    issue.rule_id,
                    {"rule_id": issue.rule_id, "severity": issue.severity,
                     "passed": 0, "failed": 0},
                )
                entry["passed" if issue.passed else "failed"] += 1
                if not issue.passed:
                    failures.append(issue)
            blocking = blockable_errors(issues)
            if blocking:
                rejected.append(
                    {
                        "source": bundle.slug,
                        "record": record.provenance.source_record_id,
                        "rules": sorted({i.rule_id for i in blocking}),
                        "messages": [i.message for i in blocking],
                    }
                )
                continue
            accepted.append(record)

    # records quarantined during import never reach staging, so the import
    # manifests are the only place that remembers them
    import_rejected = sum(
        int(manifest.get("stats", {}).get("rejected_records", 0))
        for manifest in available_bundles(settings, allowed_slugs)
    )
    validation_summary = dict(totals)
    validation_summary["rejected_records"] = len(rejected) + import_rejected
    validation_summary["rejected_in_import"] = import_rejected
    validation_summary["rejected_at_build"] = len(rejected)

    dtc_records = [r for r in accepted if isinstance(r, NormalizedDtc)]
    duplicates, duplicate_stats = detect_duplicates(dtc_records, settings.rules)
    conflicts, conflict_stats = detect_conflicts(dtc_records, settings.rules)

    db_path = settings.database_path()
    conn = create_database(db_path, settings.paths.schema)
    try:
        loader = MergeLoader(conn, settings, include_raw=include_raw)
        stats = loader.load(
            bundles,
            conflicts=conflicts,
            duplicate_groups=duplicates,
            reviews=reviews or ReviewStore.load(settings.root),
        )

        translations, translation_warnings = load_translations(
            settings, include_unreviewed=include_unreviewed_translations
        )
        warnings.extend(translation_warnings)
        applied_translations = _apply_translations(conn, translations, stats, warnings)

        # the full per-record log stays in data/staging/<source>/<commit>/validation.jsonl;
        # the database keeps the failures plus aggregate counts in the manifest.
        _store_validation_results(conn, failures)
        conn.commit()

        checks = run_database_checks(
            conn,
            source_set=source_set,
            allow_critical_conflicts=allow_critical_conflicts,
            override_reviewer=override_reviewer,
        )
        blocking_failures = failed_blocking(checks)
        try:
            optimise(conn)
        except Exception as exc:  # noqa: BLE001 - optimisation is best effort
            warnings.append(f"database optimisation skipped: {exc}")
    finally:
        counts = _counts(conn)
        conn.close()

    # ------------------------------------------------------------------
    # release gate
    # ------------------------------------------------------------------
    gate_problems: list[str] = []
    if blocking_failures:
        gate_problems.extend(f"{c.check_id}: {c.detail}" for c in blocking_failures)
    if strict and validation_summary["rejected_records"]:
        gate_problems.append(
            f"{validation_summary['rejected_records']} record(s) were quarantined by "
            "blocking validation rules"
        )
    if counts.get("dtc_codes", 0) == 0:
        gate_problems.append("the database contains no DTC codes")

    test_status = "failed" if gate_problems else "passed"

    resolved_version = version or next_version(settings.paths.exports, part)
    sources_payload = [_source_payload(settings, bundle) for bundle in bundles]

    validation_payload = {
        **validation_summary,
        "rules": [rule_counts[key] for key in sorted(rule_counts)],
        "duplicate_stats": duplicate_stats,
        "conflict_stats": conflict_stats,
        "translations_applied": applied_translations,
    }

    # a public release is a different artifact, not the same file with less
    # content: it gets its own name so the two can never be confused
    suffix = "-public" if source_set == "public" else ""
    export_path: Path | None = None
    manifest_path: Path | None = None
    app_bundle_path: Path | None = None
    app_bundle_bytes = 0
    if test_status == "passed" and export:
        export_path = settings.paths.exports / f"autodoctor-{resolved_version}{suffix}.sqlite"
        export_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(db_path, export_path)
        # the release row lives in the artifact itself, and it has to be written
        # before the manifest is hashed, otherwise the published hash would not
        # describe the published file
        _register_version(
            conn_path=export_path,
            version=resolved_version,
            built_at=_now(),
            engine_commit=commit_sha(settings.root),
            sources=sources_payload,
            counts=counts,
            validation=validation_payload,
            checks=[c.__dict__ for c in checks],
            test_status=test_status,
            # a file cannot contain the hash of itself; the authoritative
            # artifact hash is written to the manifest next to the file
            sha256=None,
            export_path=export_path,
            source_set=source_set,
        )
        if app_bundle:
            bundle_path = (
                settings.paths.exports / f"autodoctor-app-{resolved_version}{suffix}.sqlite"
            )
            try:
                built_bundle = build_app_bundle(
                    export_path, bundle_path, version=resolved_version, source_set=source_set
                )
            except LicenceError as exc:
                # the database export is already on disk: keep it for inspection,
                # refuse the release and say why
                test_status = "failed"
                gate_problems.append(str(exc))
                warnings.append(f"public bundle refused: {exc}")
            else:
                app_bundle_path = built_bundle.path
                app_bundle_bytes = built_bundle.size_bytes
                warnings.append(
                    f"app bundle: {built_bundle.path.name} ({built_bundle.size_bytes / 1e6:.1f} MB, "
                    f"{built_bundle.provenance_rows:,} provenance rows, "
                    f"source set {built_bundle.source_set})"
                )

    if test_status == "passed" and export:
        manifest = build_manifest(
            version=resolved_version,
            engine_version=engine_version,
            engine_commit=commit_sha(settings.root),
            database_path=export_path,
            sources=sources_payload,
            source_set=source_set,
            sources_excluded=excluded_sources,
            counts=counts,
            validation=validation_payload,
            checks=[c.__dict__ for c in checks],
            test_status=test_status,
            notes=(
                "D012_critical_conflicts overridden: " + allow_critical_conflicts
                if allow_critical_conflicts
                else None
            ),
            gate_overrides=(
                [
                    {
                        "gate": "D012_critical_conflicts",
                        "reason": allow_critical_conflicts,
                        "reviewer": override_reviewer,
                    }
                ]
                if allow_critical_conflicts
                else []
            ),
            warnings=warnings,
            schema_version=SCHEMA_VERSION,
            app_bundle=(
                {
                    "file": app_bundle_path.name,
                    "bytes": app_bundle_bytes,
                    "sha256": sha256_file(app_bundle_path),
                    "purpose": "Flutter client bundle (content + compact provenance)",
                }
                if app_bundle_path
                else None
            ),
        )
        manifest_path = write_manifest(
            manifest,
            settings.paths.exports / f"autodoctor-{resolved_version}{suffix}.manifest.json",
        )
    else:
        report_path = (
            settings.paths.reports / f"failed-build-{resolved_version}{suffix}.json"
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {
                    "version": resolved_version,
                    "built_at": _now(),
                    "test_status": test_status,
                    "gate_problems": gate_problems,
                    "counts": counts,
                    "validation": validation_payload,
                    "checks": [c.__dict__ for c in checks],
                    "rejected": rejected[:200],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        warnings.append(f"release blocked; details written to {report_path}")

    return BuildResult(
        version=resolved_version,
        database_path=db_path,
        export_path=export_path if test_status == "passed" else None,
        manifest_path=manifest_path,
        stats=stats.to_dict(),
        counts=counts,
        validation=validation_payload,
        checks=checks,
        conflicts=conflicts,
        duplicate_groups=duplicates,
        rejected=rejected,
        warnings=warnings + [f"release gate: {p}" for p in gate_problems],
        test_status=test_status,
        source_set=source_set,
        sources_excluded=excluded_sources,
        review_stats=getattr(loader, "review_stats", {}),
        sources=sources_payload,
        translation_entries=applied_translations,
        app_bundle_path=app_bundle_path,
        app_bundle_bytes=app_bundle_bytes,
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _counts(conn) -> dict[str, int]:
    tables = {
        "sources": "data_sources",
        "data_versions": "data_versions",
        "source_files": "source_files",
        "source_records": "source_records",
        "manufacturers": "manufacturers",
        "vehicles": "vehicles",
        "vehicle_variants": "vehicle_variants",
        "ecus": "ecus",
        "dtc_codes": "dtc_codes",
        "dtc_codes_distinct": "dtc_codes",
        "definitions": "dtc_definitions",
        "causes": "dtc_causes",
        "symptoms": "dtc_symptoms",
        "tests": "dtc_tests",
        "repairs": "dtc_repairs",
        "components": "dtc_components",
        "related_codes": "dtc_related_codes",
        "evidence": "dtc_evidence_sources",
        "pids": "pids",
        "claims": "provenance_claims",
        "conflicts": "conflicts",
        "validation_results": "validation_results",
        "duplicate_groups": "duplicate_groups",
        "translations": "translations",
    }
    counts: dict[str, int] = {}
    for label, table in tables.items():
        counts[label] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    counts["dtc_codes_distinct"] = int(
        conn.execute("SELECT COUNT(DISTINCT code) FROM dtc_codes").fetchone()[0]
    )
    counts["conflicts_open"] = int(
        conn.execute("SELECT COUNT(*) FROM conflicts WHERE status = 'needs_review'").fetchone()[0]
    )
    counts["conflicts_resolved"] = int(
        conn.execute("SELECT COUNT(*) FROM conflicts WHERE status <> 'needs_review'").fetchone()[0]
    )
    counts["definitions_verified"] = int(
        conn.execute(
            "SELECT COUNT(*) FROM dtc_definitions WHERE verification_status = 'verified'"
        ).fetchone()[0]
    )
    counts["definitions_conflicting"] = int(
        conn.execute(
            "SELECT COUNT(*) FROM dtc_definitions WHERE verification_status = 'conflicting'"
        ).fetchone()[0]
    )
    counts["codes_with_arabic"] = int(
        conn.execute("SELECT COUNT(DISTINCT dtc_code_id) FROM dtc_definitions WHERE language='ar'")
        .fetchone()[0]
    )
    return counts


def _rule_summary(issues: list[ValidationIssue]) -> list[dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for issue in issues:
        entry = summary.setdefault(
            issue.rule_id,
            {"rule_id": issue.rule_id, "severity": issue.severity, "passed": 0, "failed": 0},
        )
        entry["passed" if issue.passed else "failed"] += 1
    return [summary[key] for key in sorted(summary)]


def _store_validation_results(conn, issues: list[ValidationIssue]) -> None:
    conn.executemany(
        """
        INSERT INTO validation_results (entity_type, entity_id, entity_key, rule_id, severity,
            passed, message, created_at)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        [
            (
                issue.entity_type,
                issue.entity_id,
                issue.entity_key,
                issue.rule_id,
                issue.severity,
                int(issue.passed),
                issue.message,
                issue.created_at,
            )
            for issue in issues
        ],
    )


def _ensure_translation_source(conn) -> tuple[int, int]:
    """Register the local translation file set as a first-class source."""
    conn.execute(
        """
        INSERT INTO data_sources (slug, name, repo_url, code_license, data_license,
            attribution_required, share_alike, redistribution_allowed, commercial_use_allowed,
            legal_review_status, lineage_group, notes, created_at)
        VALUES ('local-translations', 'AutoDoctor local translations', 'local',
            'MIT', 'project-internal', 0, 0, 1, 1, 'approved', 'local-translations',
            'Human translations maintained in data/translations; never machine generated.', ?)
        ON CONFLICT(slug) DO NOTHING
        """,
        (_now(),),
    )
    source_id = int(
        conn.execute("SELECT id FROM data_sources WHERE slug = 'local-translations'").fetchone()[0]
    )
    conn.execute(
        """
        INSERT INTO data_versions (source_id, version_label, commit_sha, retrieved_at,
            file_count, record_count, content_hash)
        VALUES (?, 'working-tree', 'local', ?, 1, 0, 'local')
        ON CONFLICT(source_id, commit_sha) DO NOTHING
        """,
        (source_id, _now()),
    )
    version_id = int(
        conn.execute(
            "SELECT id FROM data_versions WHERE source_id = ? AND commit_sha = 'local'",
            (source_id,),
        ).fetchone()[0]
    )
    return source_id, version_id


def _apply_translations(conn, entries: list[TranslationEntry], stats, warnings: list[str]) -> int:
    """Attach human translations; never invent one."""
    if not entries:
        return 0
    _translation_source_id, translation_version_id = _ensure_translation_source(conn)
    applied = 0
    for entry in entries:
        row = conn.execute(
            "SELECT id FROM dtc_codes WHERE context_key = ?", (entry.context_key,)
        ).fetchone()
        if not row:
            warnings.append(
                f"translation for {entry.code} targets unknown context {entry.context_key}"
            )
            continue
        code_id = int(row[0])
        if not entry.title and not entry.description:
            continue
        content_hash = sha256_text(
            ((entry.title or "") + " — " + (entry.description or "")).casefold()
        )
        conn.execute(
            """
            INSERT INTO dtc_definitions (dtc_code_id, language, title, description, content_hash,
                is_canonical, verification_status, confidence, is_translated, translation_reviewed)
            VALUES (?,?,?,?,?,0,?,?,1,?)
            ON CONFLICT(dtc_code_id, language, content_hash) DO UPDATE SET
                translation_reviewed = excluded.translation_reviewed,
                verification_status = excluded.verification_status
            """,
            (
                code_id,
                entry.language,
                entry.title,
                entry.description,
                content_hash,
                "verified" if entry.reviewed else "unverified",
                0.8 if entry.reviewed else 0.4,
                int(entry.reviewed),
            ),
        )
        conn.execute("UPDATE dtc_definitions SET is_canonical = 0 WHERE dtc_code_id = ? "
                     "AND language = ?", (code_id, entry.language))
        conn.execute(
            """
            UPDATE dtc_definitions SET is_canonical = 1
            WHERE dtc_code_id = ? AND language = ? AND content_hash = ?
            """,
            (code_id, entry.language, content_hash),
        )
        conn.execute(
            """
            INSERT INTO translations (dtc_code_id, language, title, description, translator,
                reviewer, source_url, reviewed, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(dtc_code_id, language) DO UPDATE SET
                title = excluded.title,
                description = excluded.description,
                translator = excluded.translator,
                reviewer = excluded.reviewer,
                reviewed = excluded.reviewed
            """,
            (code_id, entry.language, entry.title, entry.description, entry.translator,
             entry.reviewer, entry.source_url, int(entry.reviewed), _now()),
        )
        definition_id = conn.execute(
            "SELECT id FROM dtc_definitions WHERE dtc_code_id = ? AND language = ? AND content_hash = ?",
            (code_id, entry.language, content_hash),
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO provenance_claims (entity_type, entity_id, attribute, source_id,
                data_version_id, source_record_id, value_hash, extraction_method, is_derived,
                is_translated, verification_status, extracted_at, notes)
            VALUES ('dtc_definition', ?, 'text', ?, ?,
                NULL, ?, 'human_translation', 1, 1, ?, ?, ?)
            """,
            (
                int(definition_id),
                _translation_source_id,
                translation_version_id,
                sha256_text(entry.file_path),
                "verified" if entry.reviewed else "unverified",
                _now(),
                f"{entry.file_path} translator={entry.translator} reviewer={entry.reviewer}",
            ),
        )
        applied += 1
        stats.claims += 1
    return applied


def _register_version(
    *,
    conn_path: Path,
    version: str,
    built_at: str,
    engine_commit: str | None,
    sources: list[dict[str, Any]],
    sha256: str | None,
    counts: dict[str, int],
    validation: dict[str, Any],
    checks: list[dict[str, Any]],
    test_status: str,
    export_path: Path,
    source_set: str = DEFAULT_SOURCE_SET,
) -> None:
    from .connection import connect

    conn = connect(conn_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO db_versions (version, built_at, git_commit, schema_version,
                    source_set, sources_json, counts_json, validation_json, sha256,
                    export_path, test_status, published_at, notes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(version) DO UPDATE SET
                    source_set = excluded.source_set,
                    counts_json = excluded.counts_json,
                    validation_json = excluded.validation_json,
                    sha256 = excluded.sha256,
                    export_path = excluded.export_path,
                    test_status = excluded.test_status,
                    published_at = excluded.published_at
                """,
                (
                    version,
                    built_at,
                    engine_commit,
                    SCHEMA_VERSION,
                    source_set,
                    json.dumps(sources, ensure_ascii=False),
                    json.dumps(counts, ensure_ascii=False),
                    json.dumps({**validation, "checks": checks}, ensure_ascii=False),
                    sha256,
                    str(export_path),
                    test_status,
                    _now() if test_status == "passed" else None,
                    "built by autodoctor-data-engine; the artifact sha256 is in the "
                    "release manifest (a file cannot contain its own hash)",
                ),
            )
    finally:
        conn.close()
