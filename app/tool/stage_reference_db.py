#!/usr/bin/env python3
"""Stage the delivered app bundle into `assets/db/` and write its manifest.

The manifest is generated from the artifact, never typed by hand: version, schema,
size and SHA-256 all come from the file that is being copied, and the view list comes
from the file's own sqlite_master. `flutter test` and the release build both rely on it.

Usage:
    python3 tool/stage_reference_db.py                # newest data/exports/autodoctor-app-*.sqlite
    python3 tool/stage_reference_db.py --bundle PATH
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_DIR.parent
ASSET_DIR = APP_DIR / "assets" / "db"


def newest_bundle() -> Path:
    candidates = sorted(
        (REPO_ROOT / "data" / "exports").glob("autodoctor-app-*.sqlite"),
        key=lambda path: path.stat().st_mtime,
    )
    if not candidates:
        raise SystemExit(
            "no app bundle found in data/exports; run `autodoctor build-db --source-set public` first"
        )
    return candidates[-1]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, default=None)
    args = parser.parse_args()

    bundle = args.bundle or newest_bundle()
    if not bundle.is_file():
        raise SystemExit(f"bundle not found: {bundle}")

    conn = sqlite3.connect(f"file:{bundle}?mode=ro", uri=True)
    try:
        version, schema = conn.execute(
            "SELECT version, schema_version FROM db_versions ORDER BY id DESC LIMIT 1"
        ).fetchone()
        views = [
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'view' ORDER BY name")
        ]
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()
    if integrity != "ok":
        raise SystemExit(f"refusing to stage a bundle that fails integrity_check: {integrity}")

    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    target = ASSET_DIR / bundle.name
    if target.resolve() != bundle.resolve():
        shutil.copyfile(bundle, target)

    manifest = {
        "version": version,
        "schema_version": int(schema),
        "file_name": target.name,
        "sha256": sha256_of(target),
        "bytes": target.stat().st_size,
        "required_views": views,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": str(bundle.relative_to(REPO_ROOT)) if bundle.is_relative_to(REPO_ROOT) else str(bundle),
    }
    manifest_path = ASSET_DIR / "db_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"staged  {target} ({manifest['bytes']:,} bytes)")
    print(f"sha256  {manifest['sha256']}")
    print(f"manifest{manifest_path} (version {version}, schema {schema}, {len(views)} views)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
