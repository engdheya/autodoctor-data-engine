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
from .config import DEFAULT_SOURCE_SET, SOURCE_SETS, ConfigError, Settings
from .conflict_resolution.detector import detect_conflicts
from .conflict_resolution.triage import render_triage_markdown, triage_conflicts, write_triage
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
from .reporting.coverage import render_coverage_markdown, write_coverage
from .reporting.report import (
    database_report,
    import_report,
    render_import_report,
    render_markdown,
    write_report,
)
from .reviews import ReviewError, ReviewStore
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
            source_set=args.source_set,
            allow_critical_conflicts=args.allow_unreviewed_critical,
            override_reviewer=getattr(args, "override_reviewer", None),
        )
    except (BuildError, ConfigError) as exc:
        _print(f"error: {exc}")
        return EXIT_FAILURE

    if args.json:
        _pretty(result.summary())
    else:
        _print(f"version:        {result.version}")
        _print(f"source set:     {result.source_set}")
        for entry in result.sources_excluded:
            _print(f"  excluded:     {entry['slug']} ({entry['reason']}, {entry['data_license']})")
        _print(f"database:       {result.database_path}")
        _print(f"status:         {result.test_status}")
        _print(f"export:         {result.export_path or '-'}")
        if result.app_bundle_path:
            _print(f"app bundle:     {result.app_bundle_path} "
                   f"({result.app_bundle_bytes / 1e6:.1f} MB)")
        _print(f"manifest:       {result.manifest_path or '-'}")
        _print("counts:")
        for key in ("dtc_codes", "dtc_codes_distinct", "definitions", "causes", "symptoms",
                    "tests", "repairs", "related_codes", "pids", "conflicts",
                    "conflicts_open", "claims", "codes_with_arabic"):
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


def cmd_review_batch(args: argparse.Namespace) -> int:
    from .conflict_resolution.triage import review_batch, write_review_batch

    settings = _settings(args)
    db_path = Path(args.database) if args.database else settings.database_path()
    if not db_path.is_file():
        _print(f"database not found: {db_path}")
        return EXIT_FAILURE
    conn = connect(db_path, readonly=True)
    try:
        batch = review_batch(conn, band=args.band, limit=args.limit)
        if args.write:
            target = (
                Path(args.out)
                if args.out
                else settings.root / "data" / "reviews" / "batches" / f"{args.band}-{args.batch:03d}.yaml"
            )
            write_review_batch(conn, target, band=args.band, limit=args.limit)
            _print(
                f"wrote {target} ({batch['queue']['in_batch']} of "
                f"{batch['queue']['band_total']} {args.band} conflicts)"
            )
            return EXIT_OK
        if args.json:
            _pretty(batch)
            return EXIT_OK
        _print(
            f"{args.band} batch: {batch['queue']['in_batch']} of "
            f"{batch['queue']['band_total']} conflicts"
        )
        for conflict in batch["conflicts"]:
            _print(f"\n{conflict['code']}  [{conflict['context_key']}]  "
                   f"similarity {conflict['similarity']}")
            for statement in conflict["statements"]:
                _print(f"  <- {statement['source']:<9} ({statement['licence']}) "
                       f"{str(statement['statement'])[:90]}")
            _print(f"  fingerprint: {conflict['fingerprint']}")
            _print(f"  decide with: {conflict['decision']['command']}")
    finally:
        conn.close()
    return EXIT_OK


def cmd_triage_conflicts(args: argparse.Namespace) -> int:
    settings = _settings(args)
    db_path = Path(args.database) if args.database else settings.database_path()
    if not db_path.is_file():
        _print(f"database not found: {db_path}")
        return EXIT_FAILURE
    conn = connect(db_path, readonly=True)
    try:
        if args.write:
            json_path, md_path = write_triage(conn, args.reports)
            _print(f"written: {json_path}\nwritten: {md_path}")
            return EXIT_OK
        report = triage_conflicts(conn)
        if args.json:
            _pretty(report)
        else:
            _print(render_triage_markdown(report, sample=args.limit))
    finally:
        conn.close()
    return EXIT_OK


def cmd_completeness(args: argparse.Namespace) -> int:
    from .reporting.completeness import completeness_report, render_completeness, write_completeness

    settings = _settings(args)
    db_path = Path(args.database) if args.database else settings.database_path()
    if not db_path.is_file():
        _print(f"database not found: {db_path}")
        return EXIT_FAILURE
    conn = connect(db_path, readonly=True)
    try:
        if args.write:
            json_path, md_path, csv_path = write_completeness(conn, args.reports)
            _print(f"written: {json_path}\nwritten: {md_path}\nwritten: {csv_path}")
            return EXIT_OK
        report = completeness_report(conn)
        if args.json:
            _pretty(report)
        else:
            _print(render_completeness(report))
    finally:
        conn.close()
    return EXIT_OK


def cmd_coverage(args: argparse.Namespace) -> int:
    settings = _settings(args)
    db_path = Path(args.database) if args.database else settings.database_path()
    if not db_path.is_file():
        _print(f"database not found: {db_path}")
        return EXIT_FAILURE
    conn = connect(db_path, readonly=True)
    try:
        if args.write:
            json_path, md_path = write_coverage(conn, args.reports)
        else:
            from .reporting.coverage import coverage_report

            report = coverage_report(conn)
            if args.json:
                _pretty(report)
                return EXIT_OK
            _print(render_coverage_markdown(report))
            return EXIT_OK
    finally:
        conn.close()
    if args.json:
        _pretty(json.loads(json_path.read_text(encoding="utf-8")))
    else:
        _print(md_path.read_text(encoding="utf-8"))
    _print(f"written: {json_path}\nwritten: {md_path}")
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
        evidence = context.get("evidence") or []
        if evidence:
            _print(f"  evidence: {len(evidence)} upstream citation(s)")
            for item in evidence[:3]:
                _print(f"    - [{item['kind']}] {item['url'][:100]}")
            if len(evidence) > 3:
                _print(f"    ... {len(evidence) - 3} more")
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
    try:
        allowed, _report = settings.resolve_source_set(args.source_set, args.source)
    except ConfigError as exc:
        _print(f"configuration error: {exc}")
        return EXIT_USAGE
    for source in settings.enabled_sources():
        if source.slug not in allowed:
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
            source_set=args.source_set,
            allow_critical_conflicts=args.allow_unreviewed_critical,
            override_reviewer=getattr(args, "override_reviewer", None),
        )
    except (BuildError, ConfigError) as exc:
        _print(f"error: {exc}")
        return EXIT_FAILURE
    _print(f"  version {result.version}: {result.test_status}")
    if result.export_path:
        _print(f"  export: {result.export_path}")
    return exit_code if result.test_status == "passed" else EXIT_FAILURE


def cmd_source_set(args: argparse.Namespace) -> int:
    settings = _settings(args)
    sets = args.set or list(SOURCE_SETS)
    payload = {name: settings.source_set_report(name) for name in sets}
    if args.json:
        _pretty(payload)
        return EXIT_OK
    for name, report in payload.items():
        _print(f"source set: {name}")
        for entry in report["included"]:
            _print(f"  include  {entry['slug']:<18} {entry['data_license']:<14} {entry['reason']}")
        for entry in report["excluded"]:
            _print(f"  EXCLUDE  {entry['slug']:<18} {entry['data_license']:<14} {entry['reason']}")
        _print()
    return EXIT_OK


def cmd_list_conflicts(args: argparse.Namespace) -> int:
    settings = _settings(args)
    db_path = settings.database_path()
    if not db_path.is_file():
        _print("no database yet; run `autodoctor build-db` first")
        return EXIT_FAILURE
    where = ["1 = 1"]
    params: list[Any] = []
    if args.status and args.status != "all":
        where.append("c.status = ?")
        params.append(args.status)
    if args.code:
        where.append("UPPER(c.code) = ?")
        params.append(args.code.upper())
    query = f"""
        SELECT c.id, c.fingerprint, c.conflict_type, c.code, c.context_key, c.attribute,
               c.summary, c.similarity, c.status, c.resolution_note
        FROM conflicts c WHERE {' AND '.join(where)}
        ORDER BY c.code, c.context_key, c.id
        LIMIT ?
    """
    params.append(args.limit)
    conn = connect(db_path, readonly=True)
    try:
        rows = conn.execute(query, params).fetchall()
        evidence: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            evidence[int(row["id"])] = [
                dict(item)
                for item in conn.execute(
                    "SELECT source_slug, value_text FROM conflict_evidence "
                    "WHERE conflict_id = ? ORDER BY source_slug",
                    (int(row["id"]),),
                )
            ]
        totals = {
            status: int(
                conn.execute(
                    "SELECT COUNT(*) FROM conflicts WHERE status = ?", (status,)
                ).fetchone()[0]
            )
            for status in ("needs_review", "resolved", "accepted_difference")
        }
    finally:
        conn.close()
    payload = {
        "totals": totals,
        "conflicts": [
            {**dict(row), "evidence": evidence[int(row["id"])]} for row in rows
        ],
    }
    if args.json:
        _pretty(payload)
        return EXIT_OK
    _print(
        f"conflicts: {totals['needs_review']:,} open, {totals['resolved']:,} resolved, "
        f"{totals['accepted_difference']:,} accepted differences"
    )
    for conflict in payload["conflicts"]:
        _print()
        _print(f"{conflict['code']}  [{conflict['context_key']}]  {conflict['conflict_type']}")
        _print(f"  fingerprint: {conflict['fingerprint']}")
        _print(f"  status:      {conflict['status']}")
        _print(f"  summary:     {conflict['summary']}")
        for item in conflict["evidence"]:
            statement = (item["value_text"] or "").replace("\n", " ")
            if len(statement) > 110:
                statement = statement[:107] + "..."
            _print(f"    <- {item['source_slug']:<10} {statement}")
        if conflict["resolution_note"]:
            _print(f"  decision:    {conflict['resolution_note']}")
    if not payload["conflicts"]:
        _print("no conflicts matched")
    _print()
    _print("resolve one with: autodoctor review-conflict <fingerprint> "
           "--accept --note '...' --reviewer 'name'")
    return EXIT_OK


def cmd_review_conflict(args: argparse.Namespace) -> int:
    settings = _settings(args)
    store = ReviewStore.load(settings.root)
    db_path = settings.database_path()
    context: dict[str, Any] = {}
    if db_path.is_file():
        conn = connect(db_path, readonly=True)
        try:
            row = conn.execute(
                "SELECT code, context_key, conflict_type FROM conflicts WHERE fingerprint = ?",
                (args.fingerprint,),
            ).fetchone()
        finally:
            conn.close()
        if row:
            context = dict(row)
    if not context and not args.force:
        _print(
            f"error: no conflict with fingerprint {args.fingerprint!r} in {db_path}. "
            "Run `autodoctor list-conflicts` to see the current fingerprints, "
            "or pass --force to record the decision anyway."
        )
        return EXIT_FAILURE

    decision = "accepted_difference" if args.accept else "resolved"
    if decision == "resolved" and not args.source:
        _print("error: --resolve needs --source <slug> naming the statement to keep")
        return EXIT_USAGE
    try:
        entry = store.record(
            fingerprint=args.fingerprint,
            decision=decision,
            note=args.note,
            reviewer=args.reviewer,
            chosen_source=args.source,
            code=context.get("code") or args.code,
            context_key=context.get("context_key"),
            conflict_type=context.get("conflict_type"),
        )
    except ReviewError as exc:
        _print(f"error: {exc}")
        return EXIT_USAGE
    _print(f"recorded {entry.decision} for {entry.fingerprint} ({entry.reviewer})")
    _print(f"stored in {store.path}")
    _print("the next build will close this conflict instead of re-opening it")
    return EXIT_OK


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
    p.add_argument("--source-set", choices=list(SOURCE_SETS), default=DEFAULT_SOURCE_SET,
                   help="licence boundary of the build: 'public' only includes sources whose "
                        "data licence and legal review allow redistribution")
    p.add_argument("--allow-unreviewed-critical", metavar="REASON",
                   help="publish despite unreviewed critical conflicts (gate D012); the reason "
                        "is recorded in the manifest and the release notes")
    p.add_argument("--override-reviewer", metavar="NAME",
                   help="who accepts the D012 override")
    p.set_defaults(func=cmd_build_db)

    p = sub.add_parser("report", help="report on the database or the imports")
    p.add_argument("--imports", action="store_true", help="report on staged imports instead")
    p.add_argument("--write", action="store_true", help="also write the report to data/reports")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("review-batch", help="export a reviewable batch of conflicts "
                                             "(band + limit) with both statements and sources")
    p.add_argument("--band", default="critical", choices=["critical", "high", "medium", "low"])
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--batch", type=int, default=1, help="batch number, used in the file name")
    p.add_argument("--database", help="database file (default: db/autodoctor.sqlite)")
    p.add_argument("--out", help="explicit output path")
    p.add_argument("--write", action="store_true", help="write the YAML batch")
    p.set_defaults(func=cmd_review_batch)

    p = sub.add_parser("completeness", help="per-code completeness: what each identity has "
                                            "and what it is missing")
    p.add_argument("--database", help="database file (default: db/autodoctor.sqlite)")
    p.add_argument("--reports", type=Path, default=Path("data/reports"))
    p.add_argument("--write", action="store_true", help="write completeness.{json,md,csv}")
    p.set_defaults(func=cmd_completeness)

    p = sub.add_parser("triage-conflicts", help="rank every open conflict into the order a "
                                                "human should review it (no decision is taken)")
    p.add_argument("--database", help="database file (default: db/autodoctor.sqlite)")
    p.add_argument("--reports", type=Path, default=Path("data/reports"))
    p.add_argument("--limit", type=int, default=15, help="rows per band in the text report")
    p.add_argument("--write", action="store_true", help="write conflict-triage.{json,md}")
    p.set_defaults(func=cmd_triage_conflicts)

    p = sub.add_parser("coverage", help="measured coverage of a built database "
                                        "(and of what it does not contain)")
    p.add_argument("--database", help="database file (default: db/autodoctor.sqlite)")
    p.add_argument("--reports", type=Path, default=Path("data/reports"),
                   help="directory for coverage.{json,md} with --write")
    p.add_argument("--write", action="store_true", help="write coverage.{json,md}")
    p.set_defaults(func=cmd_coverage)

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
    p.add_argument("--source-set", choices=list(SOURCE_SETS), default=DEFAULT_SOURCE_SET)
    p.set_defaults(func=cmd_run_all)

    p = sub.add_parser("source-set", help="show which sources a public or private build may use")
    p.add_argument("--set", action="append", choices=list(SOURCE_SETS),
                   help="limit to one set (default: both)")
    p.set_defaults(func=cmd_source_set)

    p = sub.add_parser("list-conflicts", help="review queue with stable conflict fingerprints")
    p.add_argument("--status", choices=["needs_review", "resolved", "accepted_difference", "all"],
                   default="needs_review")
    p.add_argument("--code")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_list_conflicts)

    p = sub.add_parser("review-conflict", help="record a human decision on one conflict")
    p.add_argument("fingerprint")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--accept", action="store_true",
                       help="both statements are legitimate (accepted_difference)")
    group.add_argument("--resolve", action="store_true",
                       help="one statement is correct; requires --source")
    p.add_argument("--source", help="slug of the statement to keep")
    p.add_argument("--code", help="code, when recording a decision offline")
    p.add_argument("--note", required=True, help="why this decision was taken")
    p.add_argument("--reviewer", required=True, help="who decided")
    p.add_argument("--force", action="store_true",
                   help="record a decision for a fingerprint not present in the database")
    p.set_defaults(func=cmd_review_conflict)

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
