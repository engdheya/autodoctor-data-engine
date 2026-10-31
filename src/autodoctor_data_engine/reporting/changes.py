"""Change detection between releases.

Answers the questions an updater must answer before replacing a shipped database:

  * which upstream commits moved?
  * which source records are new, changed or gone?
  * which DTC identities appeared or disappeared?

Codes that vanish from one upstream source are *reported*, never deleted: another
source may still support them, and an app update must not remove knowledge a user
may be relying on.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ..database.connection import connect


def _source_versions(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute(
        """
        SELECT s.slug, v.commit_sha FROM data_sources s
        JOIN data_versions v ON v.source_id = s.id
        """
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def _record_hashes(conn: sqlite3.Connection) -> dict[str, tuple[str, str]]:
    rows = conn.execute(
        """
        SELECT s.slug, r.source_record_id, r.raw_hash
        FROM source_records r
        JOIN source_files f ON f.id = r.source_file_id
        JOIN data_versions v ON v.id = f.data_version_id
        JOIN data_sources s ON s.id = v.source_id
        """
    ).fetchall()
    return {f"{row[0]}:{row[1]}": (row[2], row[0]) for row in rows}


def _codes(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT context_key, code FROM dtc_codes").fetchall()
    return {row[0]: row[1] for row in rows}


def detect_changes(previous: Path, current: Path, *, sample_limit: int = 20) -> dict[str, Any]:
    if not previous.is_file():
        raise FileNotFoundError(f"previous database not found: {previous}")
    prev = connect(previous, readonly=True)
    curr = connect(current, readonly=True)
    try:
        prev_versions, curr_versions = _source_versions(prev), _source_versions(curr)
        prev_records, curr_records = _record_hashes(prev), _record_hashes(curr)
        prev_codes, curr_codes = _codes(prev), _codes(curr)
    finally:
        prev.close()
        curr.close()

    moved = {
        slug: {"previous": prev_versions.get(slug), "current": curr_versions.get(slug)}
        for slug in sorted(set(prev_versions) | set(curr_versions))
        if prev_versions.get(slug) != curr_versions.get(slug)
    }

    added = sorted(set(curr_records) - set(prev_records))
    removed = sorted(set(prev_records) - set(curr_records))
    modified = sorted(
        key
        for key in set(prev_records) & set(curr_records)
        if prev_records[key][0] != curr_records[key][0]
    )

    codes_added = sorted(set(curr_codes) - set(prev_codes))
    codes_removed = sorted(set(prev_codes) - set(curr_codes))

    def per_source(keys: list[str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for key in keys:
            slug = key.split(":", 1)[0]
            counts[slug] = counts.get(slug, 0) + 1
        return dict(sorted(counts.items()))

    return {
        "previous": str(previous),
        "current": str(current),
        "sources_moved": moved,
        "records": {
            "added": len(added),
            "modified": len(modified),
            "removed": len(removed),
            "added_by_source": per_source(added),
            "modified_by_source": per_source(modified),
            "removed_by_source": per_source(removed),
            "samples": {
                "added": added[:sample_limit],
                "modified": modified[:sample_limit],
                "removed": removed[:sample_limit],
            },
        },
        "codes": {
            "added": len(codes_added),
            "removed": len(codes_removed),
            "samples_added": codes_added[:sample_limit],
            "samples_removed": codes_removed[:sample_limit],
            "note": "codes that disappear from one source are retained unless no source supports them",
        },
    }


def render_changes(report: dict[str, Any]) -> str:
    lines = ["# Change report", ""]
    lines.append(f"- previous: `{report['previous']}`")
    lines.append(f"- current:  `{report['current']}`")
    lines.append("")
    if report["sources_moved"]:
        lines.append("## Sources that moved")
        lines.append("")
        lines.append("| Source | Previous | Current |")
        lines.append("| --- | --- | --- |")
        for slug, versions in report["sources_moved"].items():
            lines.append(
                f"| {slug} | `{(versions['previous'] or '—')[:12]}` | "
                f"`{(versions['current'] or '—')[:12]}` |"
            )
        lines.append("")
    records = report["records"]
    lines.append("## Records")
    lines.append("")
    lines.append(f"- added: {records['added']:,}")
    lines.append(f"- modified: {records['modified']:,}")
    lines.append(f"- removed upstream: {records['removed']:,} (not deleted from the database)")
    lines.append("")
    if records["added_by_source"]:
        lines.append("| Source | Added | Modified | Removed |")
        lines.append("| --- | ---: | ---: | ---: |")
        for slug in sorted(set(records["added_by_source"]) | set(records["modified_by_source"])
                           | set(records["removed_by_source"])):
            lines.append(
                f"| {slug} | {records['added_by_source'].get(slug, 0):,} | "
                f"{records['modified_by_source'].get(slug, 0):,} | "
                f"{records['removed_by_source'].get(slug, 0):,} |"
            )
        lines.append("")
    codes = report["codes"]
    lines.append("## DTC identities")
    lines.append("")
    lines.append(f"- added: {codes['added']:,}")
    lines.append(f"- removed: {codes['removed']:,}")
    lines.append("")
    lines.append(f"> {codes['note']}")
    return "\n".join(lines)
