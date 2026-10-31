"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from helpers import FIXTURES, REPO_ROOT, create_project

from autodoctor_data_engine.config import Settings

__all__ = ["REPO_ROOT", "FIXTURES", "project_root", "settings", "imported", "built",
           "db_conn", "fresh_project"]


@pytest.fixture(scope="session")
def project_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return create_project(tmp_path_factory.mktemp("autodoctor-project"))


@pytest.fixture(scope="session")
def settings(project_root: Path) -> Settings:
    return Settings(root=project_root)


@pytest.fixture(scope="session")
def imported(settings: Settings) -> Settings:
    """All four sources imported and staged once for the whole session."""
    from autodoctor_data_engine.pipeline import import_source

    for slug in ("obdex", "wal33d", "autodiag", "obdb"):
        import_source(settings, slug)
    return settings


@pytest.fixture(scope="session")
def built(imported: Settings):
    """A published database built from the staged fixtures."""
    from autodoctor_data_engine.database.build import build_database

    return build_database(imported, version="0.1.0")


@pytest.fixture(scope="session")
def db_conn(built):
    from autodoctor_data_engine.database.connection import connect

    conn = connect(built.database_path, readonly=True)
    yield conn
    conn.close()


@pytest.fixture
def fresh_project(tmp_path: Path) -> Path:
    """A pristine project per test (for anything that mutates state)."""
    return create_project(tmp_path / "project")
