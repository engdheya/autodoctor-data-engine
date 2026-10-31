"""Optional checks against the real upstream checkouts.

They are skipped unless ``AUTODOCTOR_INTEGRATION=1`` and the sources have been
fetched (``autodoctor fetch-sources``). They are intentionally shallow: the full
import of all four sources takes minutes and belongs in the release workflow.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from autodoctor_data_engine.config import Settings
from autodoctor_data_engine.connectors import build_connector
from autodoctor_data_engine.models import NormalizedDtc

pytestmark = pytest.mark.integration

requires_integration = pytest.mark.skipif(
    os.environ.get("AUTODOCTOR_INTEGRATION") != "1",
    reason="set AUTODOCTOR_INTEGRATION=1 (and fetch the sources) to run",
)

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def real_settings() -> Settings:
    settings = Settings(root=REPO_ROOT)
    missing = [s.slug for s in settings.enabled_sources() if not s.local_path.is_dir()]
    if missing:
        pytest.skip(f"upstream checkouts missing: {missing}")
    return settings


@requires_integration
def test_obdex_real_layout(real_settings: Settings) -> None:
    connector = build_connector(real_settings, "obdex")
    inspection = connector.inspect()
    assert inspection.present
    assert inspection.layout["dtc_entries"] > 9000
    raw = next(connector.extract())
    (record,) = connector.normalize(raw, connector.provenance_base(raw, "0" * 40))
    assert isinstance(record, NormalizedDtc)
    assert record.definitions


@requires_integration
def test_wal33d_real_sqlite(real_settings: Settings) -> None:
    connector = build_connector(real_settings, "wal33d")
    inspection = connector.inspect()
    assert inspection.layout["rows"] > 18000
    assert inspection.layout["unique_codes"] > 12000
    assert len(inspection.layout["manufacturers"]) > 30


@requires_integration
def test_autodiag_real_tree(real_settings: Settings) -> None:
    connector = build_connector(real_settings, "autodiag")
    inspection = connector.inspect()
    assert inspection.layout["code_files"] > 28000
    assert inspection.layout["unique_codes"] > 16000


@requires_integration
def test_obdb_real_repositories(real_settings: Settings) -> None:
    connector = build_connector(real_settings, "obdb")
    inspection = connector.inspect()
    assert inspection.layout["dtc_definitions"] == 0
    assert inspection.layout["signals"] > 0
