"""Source connectors: one per upstream project."""

from .autodiag import AutodiagConnector
from .base import ConnectorError, RawRecord, SourceConnector, SourceInspection
from .obdb import ObdbConnector
from .obdex import ObdexConnector
from .registry import CONNECTORS, all_connectors, build_connector
from .wal33d import Wal33DConnector

__all__ = [
    "SourceConnector",
    "RawRecord",
    "SourceInspection",
    "ConnectorError",
    "ObdexConnector",
    "Wal33DConnector",
    "AutodiagConnector",
    "ObdbConnector",
    "CONNECTORS",
    "build_connector",
    "all_connectors",
]
