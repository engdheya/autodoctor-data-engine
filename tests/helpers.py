"""Helpers to build miniature AutoDoctor projects for the tests."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"

SOURCES_YAML = """\
project:
  name: AutoDoctor test project
  database_filename: autodoctor.sqlite

paths:
  raw: data/raw
  staging: data/staging
  processed: data/processed
  exports: data/exports
  reports: data/reports
  upstream: vendor/upstream

sources:
  - slug: obdex
    name: OBDex fixture
    repo_url: https://github.com/foerbsnavi/OBDex
    local_path: vendor/upstream/OBDex
    kind: obdex
    enabled: true
    licence:
      code: MIT
      data: CC0-1.0
      attribution_required: false
      share_alike: false
      redistribution_allowed: true
      commercial_use_allowed: true
      legal_review: approved
    lineage: obdex
    import_scope: [dtc, pid]

  - slug: wal33d
    name: Wal33D fixture
    repo_url: https://github.com/Wal33D/dtc-database
    local_path: vendor/upstream/dtc-database
    kind: wal33d
    enabled: true
    licence:
      code: MIT
      data: MIT
      attribution_required: true
      share_alike: false
      redistribution_allowed: true
      commercial_use_allowed: true
      legal_review: approved
    lineage: wal33d
    import_scope: [dtc]

  - slug: autodiag
    name: autodiag2 fixture
    repo_url: https://github.com/autodiag2/database
    local_path: vendor/upstream/autodiag2-database
    kind: autodiag
    enabled: true
    licence:
      code: GPL-3.0-or-later
      data: ODbL-1.0
      attribution_required: true
      share_alike: true
      redistribution_allowed: true
      commercial_use_allowed: true
      legal_review: pending
    lineage: obdcodex
    import_scope: [dtc, ecu, vehicle]

  - slug: obdb
    name: OBDb fixture
    repo_url: https://github.com/OBDb
    local_path: vendor/upstream/OBDb
    kind: obdb
    enabled: true
    licence:
      code: CC-BY-SA-4.0
      data: CC-BY-SA-4.0
      attribution_required: true
      share_alike: true
      redistribution_allowed: true
      commercial_use_allowed: true
      legal_review: pending
    lineage: obdb
    import_scope: [vehicle, ecu, pid]

rules:
  code_pattern: '^[PBCU][0-3][0-9A-F]{3}$'
  uds_code_pattern: '^[0-9A-F]{6,8}$'
  similarity_threshold: 0.85
  min_corroborating_lineages: 2
  blocked_redistribution_review: [autodiag, obdb]
"""


def _build_wal33d_db(target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    try:
        conn.executescript((FIXTURES / "wal33d" / "seed.sql").read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()


def create_project(root: Path, *, with_upstream: bool = True) -> Path:
    """Materialise a miniature project under ``root`` and return ``root``."""
    root = Path(root)
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "sources.yaml").write_text(SOURCES_YAML, encoding="utf-8")
    (root / "db").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO_ROOT / "db" / "schema.sql", root / "db" / "schema.sql")
    shutil.copytree(FIXTURES / "translations", root / "data" / "translations",
                    dirs_exist_ok=True)
    if not with_upstream:
        return root

    upstream = root / "vendor" / "upstream"
    upstream.mkdir(parents=True, exist_ok=True)
    shutil.copytree(FIXTURES / "obdex", upstream / "OBDex", dirs_exist_ok=True)
    shutil.copytree(FIXTURES / "autodiag", upstream / "autodiag2-database", dirs_exist_ok=True)
    shutil.copytree(FIXTURES / "wal33d", upstream / "dtc-database", dirs_exist_ok=True)
    _build_wal33d_db(upstream / "dtc-database" / "data" / "dtc_codes.db")
    shutil.copytree(FIXTURES / "obdb", upstream / "OBDb", dirs_exist_ok=True)
    return root
