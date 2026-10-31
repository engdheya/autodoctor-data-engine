"""Connector registry."""

from __future__ import annotations

from ..config import Settings, SourceConfig
from .autodiag import AutodiagConnector
from .base import SourceConnector
from .obdb import ObdbConnector
from .obdex import ObdexConnector
from .wal33d import Wal33DConnector

CONNECTORS: dict[str, type[SourceConnector]] = {
    "obdex": ObdexConnector,
    "wal33d": Wal33DConnector,
    "autodiag": AutodiagConnector,
    "obdb": ObdbConnector,
}


def build_connector(settings: Settings, slug: str) -> SourceConnector:
    source: SourceConfig = settings.source(slug)
    try:
        cls = CONNECTORS[source.kind]
    except KeyError as exc:
        raise KeyError(
            f"no connector registered for kind {source.kind!r} (source {slug!r}); "
            f"known kinds: {', '.join(sorted(CONNECTORS))}"
        ) from exc
    return cls(settings, source)


def all_connectors(settings: Settings, enabled_only: bool = True) -> list[SourceConnector]:
    sources = settings.enabled_sources() if enabled_only else list(settings.sources.values())
    return [build_connector(settings, source.slug) for source in sources]
