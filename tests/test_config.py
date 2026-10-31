"""The source registry is the contract that makes provenance enforceable."""

from __future__ import annotations

import pytest
from helpers import create_project

from autodoctor_data_engine.config import ConfigError, Settings, find_project_root


def test_settings_loads_every_source(settings: Settings) -> None:
    assert set(settings.sources) == {"obdex", "wal33d", "autodiag", "obdb"}
    assert settings.sources["obdex"].licence.data == "CC0-1.0"
    assert settings.sources["autodiag"].licence.share_alike is True
    assert settings.sources["autodiag"].licence.legal_review == "pending"


def test_paths_are_resolved_inside_the_project(settings: Settings) -> None:
    assert settings.paths.raw == settings.root / "data" / "raw"
    assert settings.paths.schema.is_file()
    assert settings.paths.database.name == "autodoctor.sqlite"


def test_unknown_source_raises(settings: Settings) -> None:
    with pytest.raises(ConfigError):
        settings.source("not-a-source")


def test_missing_registry_raises(tmp_path) -> None:
    with pytest.raises(ConfigError):
        Settings(root=tmp_path)


def test_find_project_root_uses_environment(tmp_path, monkeypatch) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "sources.yaml").write_text("sources: []\n", encoding="utf-8")
    monkeypatch.setenv("AUTODOCTOR_ROOT", str(tmp_path))
    assert find_project_root() == tmp_path.resolve()


def test_disabled_sources_are_skipped(tmp_path) -> None:
    root = create_project(tmp_path / "p")
    config_path = root / "config" / "sources.yaml"
    text = config_path.read_text(encoding="utf-8")
    text = text.replace(
        "    kind: obdb\n    enabled: true", "    kind: obdb\n    enabled: false"
    )
    config_path.write_text(text, encoding="utf-8")

    settings = Settings(root=root)
    assert "obdb" not in [s.slug for s in settings.enabled_sources()]
    assert len(settings.sources) == 4


def test_environment_variable_expansion(tmp_path, monkeypatch) -> None:
    root = create_project(tmp_path / "p", with_upstream=False)
    config_path = root / "config" / "sources.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "local_path: vendor/upstream/OBDex",
            "local_path: ${AUTODOCTOR_TEST_UPSTREAM:-elsewhere}/OBDex",
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AUTODOCTOR_TEST_UPSTREAM", "custom/upstream")
    settings = Settings(root=root)
    assert settings.sources["obdex"].local_path == (root / "custom/upstream/OBDex").resolve()
