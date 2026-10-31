"""Command line interface.

    autodoctor inspect-sources
    autodoctor import --source obdex
    autodoctor validate
    autodoctor detect-duplicates
    autodoctor build-db --version 0.1.0
    autodoctor report
    autodoctor version
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .config import ConfigError, Settings
from .conflict_resolution.detector import detect_conflicts
from .database.build import BuildError, build_database
from .database.connection import connect
from .deduplication.detector import detect_duplicates
from .models import NormalizedDtc
from .pipeline import (
    ImportRejected,
    fetch_sources,
    import_source,
    inspect_sources,
    validate_staged,
    write_inspection_report,
)
from .provenance.tracker import ProvenanceTracker
from .reporting.changes import detect_changes, render_changes
from .reporting.report import (
    database_report,
    import_report,
    render_import_report,
    render_markdown,
    write_report,
)
from .staging import load_all_bundles
from .translations import export_template
from .versioning.manifest import latest_manifest

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _print(message: str = "") -> None:
    print(message)


def _pretty(payload: Any) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _settings(args: argparse.Namespace) -> Settings:
    root = Path(args.root).expanduser().resolve() if args.root else None
    return Settings(root=root)


def _record_counts(bundles) -> dict[str, int]:
    counts: dict[str, int] = {}
    for bundle in bundles:
        for record in bundle.records:
            counts[record.record_type] = counts.get(record.record_type, 0) + 1
    return counts


def _dtc_records(bundles) -> list[NormalizedDtc]:
    return [r for b in bundles for r in b.records if isinstance(r, NormalizedDtc)]


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_inspect(args: argparse.Namespace) -> int:
    settings = _settings(args)
    inspections = inspect_sources(settings, args.source or None)
    if args.json:
        _pretty({"sources": [i.to_dict() for i in inspections]})
    else:
        for inspection in inspections:
            status = "OK" if inspection.present else "MISSING"
            _print(f"[{status}] {inspection.slug}  ({inspection.name})")
            _print(f"    path:   {inspection.local_path}")
            _print(f"    commit: {inspection.commit_sha or '-'}  label: {inspection.describe or '-'}"
                   f"  dirty: {inspection.dirty}")
            _print(f"    files:  {inspection.file_count}  bytes: {inspection.total_bytes:,}")
            _print(
                f"    licence: code={inspection.licence.get('code')} "
                f"data={inspection.licence.get('data')} "
                f"review={inspection.licence.get('legal_review')} "
                f"share_alike={inspection.licence.get('share_alike')}"
            )
            layout = inspection.layout or {}
            for key in ("format", "dtc_entries", "rows", "unique_codes", "code_files",
                        "repositories", "signals", "dtc_definitions"):
                if key in layout:
                    _print(f"    {key}: {layout[key]}")
            for warning in inspection.warnings:
                _print(f"    ! {warning}")
            _print()
    report_path = write_inspection_report(settings, inspections)
    if not args.json:
        _print(f"report: {report_path}")
    missing = [i.slug for i in inspections if not i.present]
    if missing and len(missing) == len(inspections):
        return EXIT_FAILURE
    return EXIT_OK


def cmd_fetch(args: argparse.Namespace) -> int:
    settings = _settings(args)
    outcome = fetch_sources(settings, args.source or None, limit=args.limit)
    _pretty(outcome)
    return EXIT_OK if all("failed" not in v for v in outcome.values()) else EXIT_FAILURE


def cmd_import(args: argparse.Namespace) -> int:
    settings = _settings(args)
    slugs = args.source or []
    if args.all:
        slugs = [s.slug for s in settings.enabled_sources()]
    if not slugs:
        _print("error: pass --source <slug> or --all")
        return EXIT_USAGE

    results = []
    exit_code = EXIT_OK
    for slug in slugs:
        _print(f"importing {slug} ...")
        try:
            result = import_source(
                settings, slug, fail_on_error=args.fail_on_error, limit=args.limit
            )
        except ImportRejected as exc:
            _print(f"  ! rejected: {exc}")
            for sample in exc.samples:
                _print(f"    - {sample['record']}: {sample['rules']}")
            exit_code = EXIT_FAILURE
            continue
        except Exception as exc:  # noqa: BLE001 - report and continue with other sources
            _print(f"  ! failed: {exc}")
            exit_code = EXIT_FAILURE
            continue
        results.append(result.to_dict())
        _print(
            f"  raw records: {result.records_raw}  normalized: {result.records_normalized}  "
            f"files: {result.files}  rejected: {result.rejected}"
        )
        _print(f"  record types: {json.dumps(result.record_counts)}")
        _print(f"  manifest: {result.manifest_path}")
        for warning in result.warnings:
            _print(f"  ! {warning}")

    if args.json:
        _pretty({"imports": results})
    return exit_code


def cmd_validate(args: argparse.Namespace) -> int:
    settings = _settings(args)
    summary = validate_staged(settings, args.source or None)
    if args.json:
        _pretty(summary)
    else:
        if not summary["sources"]:
            _print("no staged imports; run `autodoctor import --all` first")
            return EXIT_FAILURE
        _print(f"{'source':<12}{'records':>10}{'rejected':>10}{'checks':>10}"
               f"{'errors':>10}{'warnings':>10}")
        for slug, data in summary["sources"].items():
            _print(
                f"{slug:<12}{data.get('records', 0):>10,}{data.get('rejected', 0):>10,}"
                f"{data.get('passed', 0) + data.get('failed', 0):>10,}"
                f"{data.get('errors', 0):>10,}{data.get('warnings', 0):>10,}"
            )
        totals = summary["totals"]
        _print(
            f"{'TOTAL':<12}{totals['records']:>10,}{totals['rejected']:>10,}"
            f"{'':>10}{totals['errors']:>10,}{totals['warnings']:>10,}"
        )
        if totals["rejected"] or totals["errors"]:
            _print("\nblocking problems detected; `autodoctor report` lists the rules involved")
            return EXIT_FAILURE
    return EXIT_OK if not summary["totals"].get("rejected") else EXIT_FAILURE


def cmd_detect_duplicates(args: argparse.Namespace) -> int:
    settings = _settings(args)
    bundles = load_all_bundles(settings, args.source or None)
    records = _dtc_records(bundles)
    if not records:
        _print("no staged DTC records; run `autodoctor import --all` first")
        return EXIT_FAILURE
    groups, stats = detect_duplicates(records, settings.rules)
    by_type: dict[str, list[dict[str, Any]]] = {}
    for group in groups:
        by_type.setdefault(group.match_type, []).append(group.to_dict())
    if args.json:
        _pretty({"stats": stats, "groups": by_type})
    else:
        _print(f"statements compared: {stats['statements']:,}")
        _print(f"exact duplicate groups: {stats['exact']:,}")
        _print(f"near duplicate groups:  {stats['near']:,}")
        _print(f"codes defined in several contexts (not duplicates): "
               f"{stats['context_variants']:,}")
        _print()
        for kind in ("exact_statement", "near_statement", "code_context_variants"):
            samples = by_type.get(kind, [])[: args.limit]
            if not samples:
                continue
            _print(f"--- {kind} (showing {len(samples)}) ---")
            for group in samples:
                _print(f"  * {group['reason']}")
                for member in group["members"][:4]:
                    _print(f"      - {member}")
            _print()
    return EXIT_OK


def cmd_detect_conflicts(args: argparse.Namespace) -> int:
    settings = _settings(args)
    bundles = load_all_bundles(settings, args.source or None)
    records = _dtc_records(bundles)
    if not records:
        _print("no staged DTC records; run `autodoctor import --all` first")
        return EXIT_FAILURE
    conflicts, stats = detect_conflicts(records, settings.rules)
    if args.json:
        _pretty(
            {
                "stats": stats,
                "conflicts": [c.to_dict() for c in conflicts[: args.limit]],
                "total": len(conflicts),
            }
        )
    else:
        _print(f"conflicts detected: {len(conflicts):,}")
        for kind, count in sorted(stats.items()):
            _print(f"  {kind}: {count:,}")
        _print()
        for conflict in conflicts[: args.limit]:
            _print(f"* {conflict.summary}")
            for evidence in conflict.evidence:
                _print(f"    [{evidence.source_slug}] {evidence.value[:160]}")
        if len(conflicts) > args.limit:
            _print(f"\n... {len(conflicts) - args.limit:,} more (use --limit)")
    return EXIT_OK


def cmd_build_db(args: argparse.Namespace) -> int:
    settings = _settings(args)
    try:
        result = build_database(
            settings,
            version=args.version,
            part=args.part,
            slugs=args.source or None,
            include_raw=args.include_raw,
            include_unreviewed_translations=args.include_unreviewed_translations,
            strict=args.strict,
            export=not args.no_export,
            app_bundle=not args.no_app_bundle,
        )
    except BuildError as exc:
        _print(f"error: {exc}")
        return EXIT_FAILURE

    if args.json:
        _pretty(result.summary())
    else:
        _print(f"version:        {result.version}")
        _print(f"database:       {result.database_path}")
        _print(f"status:         {result.test_status}")
        _print(f"export:         {result.export_path or '-'}")
        if result.app_bundle_path:
            _print(f"app bundle:     {result.app_bundle_path} "
                   f"({result.app_bundle_bytes / 1e6:.1f} MB)")
        _print(f"manifest:       {result.manifest_path or '-'}")
        _print("counts:")
        for key in ("dtc_codes", "dtc_codes_distinct", "definitions", "causes", "symptoms",
                    "tests", "repairs", "related_codes", "pids", "conflicts", "claims",
                    "codes_with_arabic"):
            _print(f"  {key:<22}{result.counts.get(key, 0):>10,}")
        failures = [c for c in result.checks if c.blocking and not c.passed]
        _print(f"release checks:  {len([c for c in result.checks if c.passed])}/"
               f"{len(result.checks)} passed")
        for check in result.checks:
            marker = "ok  " if check.passed else ("FAIL" if check.blocking else "warn")
            _print(f"  [{marker}] {check.check_id}: {check.description} ({check.detail})")
        for warning in result.warnings:
            _print(f"  ! {warning}")
        if failures:
            _print("\nrelease blocked by failing gates; the exported database was not produced")
    return EXIT_OK if result.test_status == "passed" else EXIT_FAILURE


def cmd_report(args: argparse.Namespace) -> int:
    settings = _settings(args)
    if args.imports:
        report = import_report(settings)
        text = render_import_report(report)
    else:
        db_path = settings.database_path()
        if not db_path.is_file():
            _print("no database yet; run `autodoctor build-db` first")
            return EXIT_FAILURE
        conn = connect(db_path, readonly=True)
        try:
            report = database_report(settings, conn)
        finally:
            conn.close()
        text = render_markdown(report)
    if args.json:
        _pretty(report)
    else:
        _print(text)
    if args.write:
        prefix = "import-report" if args.imports else "data-report"
        json_path, md_path = write_report(settings, report, prefix=prefix)
        _print(f"\nwritten: {json_path}\nwritten: {md_path}")
    return EXIT_OK


def cmd_version(args: argparse.Namespace) -> int:
    settings = _settings(args)
    manifest = latest_manifest(settings.paths.exports) if settings.paths.exports.is_dir() else None
    payload: dict[str, Any] = {
        "engine_version": __version__,
        "database": str(settings.database_path()),
        "database_exists": settings.database_path().is_file(),
        "release": None,
    }
    if manifest:
        payload["release"] = {
            key: manifest.get(key)
            for key in ("version", "built_at", "test_status", "database_sha256",
                        "database_bytes", "engine_commit")
        }
        payload["release"]["sources"] = [
            {"slug": s["slug"], "commit": s["commit_sha"], "licence": s["data_license"]}
            for s in manifest.get("sources", [])
        ]
    if args.json:
        _pretty(payload)
    else:
        _print(f"engine:   {payload['engine_version']}")
        _print(f"database: {payload['database']} (exists: {payload['database_exists']})")
        if manifest:
            _print(f"release:  {manifest['version']}  built {manifest['built_at']}  "
                   f"status {manifest['test_status']}")
            _print(f"sha256:   {manifest['database_sha256']}")
            for source in manifest.get("sources", []):
                _print(f"  source {source['slug']:<10} {(source['commit_sha'] or '')[:12]}  "
                       f"{source['data_license']}")
        else:
            _print("release:  none (no published export found)")
    return EXIT_OK


def cmd_search(args: argparse.Namespace) -> int:
    settings = _settings(args)
    db_path = settings.database_path()
    if not db_path.is_file():
        _print("no database; run `autodoctor build-db` first")
        return EXIT_FAILURE
    conn = connect(db_path, readonly=True)
    try:
        rows = conn.execute(
            "SELECT * FROM v_dtc_summary WHERE code = ? ORDER BY context_type, manufacturer",
            (args.code.strip().upper(),),
        ).fetchall()
        if not rows:
            _print(f"{args.code}: not found")
            return EXIT_FAILURE
        payload = [dict(row) for row in rows]
        if args.json:
            _pretty(payload)
            return EXIT_OK
        for row in payload:
            context = row["context_type"]
            if row["manufacturer"]:
                context += f": {row['manufacturer']}"
            _print(f"{row['code']}  [{context}]")
            _print(f"  EN: {row['title_en'] or '-'}")
            if row["title_ar"]:
                _print(f"  AR: {row['title_ar']}")
            _print(f"  causes: {row['cause_count']}  symptoms: {row['symptom_count']}  "
                   f"tests: {row['test_count']}  repairs: {row['repair_count']}  "
                   f"sources: {row['source_count']}")
            if row["risk_level"]:
                _print(f"  risk: {row['risk_level']}")
            _print()
    finally:
        conn.close()
    _print("Reminder: a DTC identifies a fault *area*, not a failed part. "
           "Always confirm with the listed tests.")
    return EXIT_OK


def cmd_explain(args: argparse.Namespace) -> int:
    settings = _settings(args)
    db_path = settings.database_path()
    if not db_path.is_file():
        _print("no database; run `autodoctor build-db` first")
        return EXIT_FAILURE
    conn = connect(db_path, readonly=True)
    try:
        tracker = ProvenanceTracker(conn)
        payload = tracker.explain_code(
            args.code, context_key=args.context, language=args.lang
        )
    finally:
        conn.close()
    if args.json:
        _pretty(payload)
        return EXIT_OK if payload["found"] else EXIT_FAILURE
    if not payload["found"]:
        _print(f"{args.code}: not found")
        return EXIT_FAILURE
    for context in payload["contexts"]:
        _print(f"{payload['code']}  [{context['context_type']}]  {context['context_key']}")
        _print(f"  standard: {context['standard']}  protocol: {context['protocol']}")
        for definition in context["definitions"]:
            marker = "*" if definition["is_canonical"] else " "
            _print(f"  {marker} {definition['language']}: "
                   f"{definition['title'] or definition['description'] or '-'}")
            _print(f"      status: {definition['verification_status']} "
                   f"(confidence {definition['confidence']})")
            for claim in definition["claims"]:
                commit = (claim["commit_sha"] or "")[:12]
                _print(f"      <- {claim['source']} @ {commit} | licence "
                       f"{claim['data_license']} | {claim['extracted_at']}")
                if claim["file_path"]:
                    _print(f"         file {claim['file_path']} record {claim['source_record_id']}")
        for conflict in context["conflicts"]:
            _print(f"  ! conflict: {conflict['summary']}")
            for evidence in conflict["evidence"]:
                _print(f"      [{evidence['source']}] {evidence['value'][:120]}")
        if context["counts"]:
            _print("  content: " + ", ".join(f"{k}={v}" for k, v in context["counts"].items()))
        _print()
    return EXIT_OK


def cmd_detect_changes(args: argparse.Namespace) -> int:
    settings = _settings(args)
    current = Path(args.current) if args.current else settings.database_path()
    previous = Path(args.previous) if args.previous else None
    if previous is None:
        exports = sorted(
            settings.paths.exports.glob("autodoctor-*.sqlite"),
            key=lambda p: p.stat().st_mtime,
        )
        exports = [p for p in exports if p.resolve() != current.resolve()]
        if not exports:
            _print("no previous release found; pass --previous <file>")
            return EXIT_FAILURE
        previous = exports[-1]
    report = detect_changes(previous, current)
    if args.json:
        _pretty(report)
    else:
        _print(render_changes(report))
    return EXIT_OK


def cmd_translation_template(args: argparse.Namespace) -> int:
    settings = _settings(args)
    db_path = settings.database_path()
    if not db_path.is_file():
        _print("no database; run `autodoctor build-db` first")
        return EXIT_FAILURE
    path = settings.paths.reports / f"translation-template-{args.lang}.csv"
    conn = connect(db_path, readonly=True)
    try:
        count = export_template(conn, path, language=args.lang, limit=args.limit)
    finally:
        conn.close()
    _print(f"wrote {count:,} rows to {path}")
    _print("Fill in the translated columns, set reviewed: true with a reviewer, then place "
           "the YAML in data/translations/<lang>/ and rebuild.")
    return EXIT_OK


def cmd_run_all(args: argparse.Namespace) -> int:
    settings = _settings(args)
    exit_code = EXIT_OK
    for source in settings.enabled_sources():
        if args.source and source.slug not in args.source:
            continue
        _print(f"importing {source.slug} ...")
        try:
            result = import_source(settings, source.slug)
        except Exception as exc:  # noqa: BLE001
            _print(f"  ! {exc}")
            exit_code = EXIT_FAILURE
            continue
        _print(f"  {result.records_normalized:,} records normalized "
               f"({result.rejected:,} rejected)")
    _print("building database ...")
    try:
        result = build_database(
            settings,
            version=args.version,
            part=args.part,
            strict=args.strict,
            export=not args.no_export,
        )
    except BuildError as exc:
        _print(f"error: {exc}")
        return EXIT_FAILURE
    _print(f"  version {result.version}: {result.test_status}")
    if result.export_path:
        _print(f"  export: {result.export_path}")
    return exit_code if result.test_status == "passed" else EXIT_FAILURE


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autodoctor",
        description="AutoDoctor AI - automotive DTC data integration engine",
    )
    parser.add_argument("--root", help="project root (defaults to the current directory)")
    parser.add_argument("--json", action="store_true", help="machine readable output")
    parser.add_argument("--version", action="version", version=f"autodoctor {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("inspect-sources", help="describe every configured source")
    p.add_argument("--source", action="append", help="limit to one source (repeatable)")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("fetch-sources", help="clone upstream checkouts into vendor/upstream")
    p.add_argument("--source", action="append")
    p.add_argument("--limit", type=int, default=5, help="OBDb repositories to clone")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("import", help="extract, archive and normalize a source")
    p.add_argument("--source", action="append")
    p.add_argument("--all", action="store_true")
    p.add_argument("--fail-on-error", action="store_true",
                   help="abort when a record fails a blocking validation rule")
    p.add_argument("--limit", type=int, help="only import the first N raw records (debugging)")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("validate", help="summarize validation results of the staged imports")
    p.add_argument("--source", action="append")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("detect-duplicates", help="find duplicate statements and code/context variants")
    p.add_argument("--source", action="append")
    p.add_argument("--limit", type=int, default=5)
    p.set_defaults(func=cmd_detect_duplicates)

    p = sub.add_parser("detect-conflicts", help="find statements that contradict each other")
    p.add_argument("--source", action="append")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_detect_conflicts)

    p = sub.add_parser("build-db", help="merge the staged records into SQLite and publish a release")
    p.add_argument("--version", help="explicit release version (e.g. 0.1.0)")
    p.add_argument("--part", choices=["major", "minor", "patch"], default="patch")
    p.add_argument("--source", action="append")
    p.add_argument("--include-raw", action="store_true", help="also store raw JSON inside SQLite")
    p.add_argument("--include-unreviewed-translations", action="store_true")
    p.add_argument("--strict", action="store_true",
                   help="block the release when any record was quarantined by validation")
    p.add_argument("--no-export", action="store_true", help="build the working database only")
    p.add_argument("--no-app-bundle", action="store_true",
                   help="skip the compact Flutter bundle")
    p.set_defaults(func=cmd_build_db)

    p = sub.add_parser("report", help="report on the database or the imports")
    p.add_argument("--imports", action="store_true", help="report on staged imports instead")
    p.add_argument("--write", action="store_true", help="also write the report to data/reports")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("version", help="show the engine and database release version")
    p.set_defaults(func=cmd_version)

    p = sub.add_parser("search", help="look up a DTC in the built database")
    p.add_argument("code")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("explain", help="show every source behind a DTC")
    p.add_argument("code")
    p.add_argument("--context", help="restrict to one context_key")
    p.add_argument("--lang", help="restrict to one language")
    p.set_defaults(func=cmd_explain)

    p = sub.add_parser("detect-changes", help="diff two database builds")
    p.add_argument("--previous")
    p.add_argument("--current")
    p.set_defaults(func=cmd_detect_changes)

    p = sub.add_parser("export-translation-template",
                       help="CSV of generic codes that still need a translation")
    p.add_argument("--lang", default="ar")
    p.add_argument("--limit", type=int)
    p.set_defaults(func=cmd_translation_template)

    p = sub.add_parser("run-all", help="import every enabled source and build the database")
    p.add_argument("--version")
    p.add_argument("--part", choices=["major", "minor", "patch"], default="patch")
    p.add_argument("--source", action="append")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--no-export", action="store_true")
    p.set_defaults(func=cmd_run_all)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or EXIT_OK)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except KeyboardInterrupt:  # pragma: no cover
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
