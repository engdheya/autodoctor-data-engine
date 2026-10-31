"""Connector contract.

A connector has exactly two responsibilities:

1. ``extract()`` - enumerate the upstream records verbatim, together with the file
   they came from and their native identifier. No cleaning happens here.
2. ``normalize()`` - map one raw record into the shared intermediate model. All
   string/code/manufacturer normalization goes through ``normalizers.*``.

Everything else (raw archiving, hashing, validation, dedup, merging) is done by
the pipeline, so a new source cannot accidentally skip provenance.
"""

from __future__ import annotations

import abc
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

from ..config import Settings, SourceConfig
from ..models import NormalizedRecord
from ..utils.hashing import sha256_json


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ConnectorError(RuntimeError):
    """Raised when a source checkout is missing or unusable."""


@dataclass
class RawRecord:
    record_type: str
    source_record_id: str
    file_path: str
    payload: Any
    extra: dict[str, Any] = field(default_factory=dict)

    def payload_hash(self) -> str:
        return sha256_json({"payload": self.payload, "extra": self.extra})


@dataclass
class VersionInfo:
    """Cheap version metadata, without parsing the whole source."""

    commit: str | None
    label: str | None
    dirty: bool
    warnings: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceInspection:
    slug: str
    name: str
    repo_url: str
    local_path: str
    present: bool
    commit_sha: str | None
    describe: str | None
    dirty: bool
    file_count: int
    total_bytes: int
    layout: dict[str, Any]
    licence: dict[str, Any]
    notes: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "name": self.name,
            "repo_url": self.repo_url,
            "local_path": self.local_path,
            "present": self.present,
            "commit_sha": self.commit_sha,
            "describe": self.describe,
            "dirty": self.dirty,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
            "layout": self.layout,
            "licence": self.licence,
            "notes": self.notes,
            "warnings": self.warnings,
        }


class SourceConnector(abc.ABC):
    """Base class for all source connectors."""

    slug: ClassVar[str] = ""
    record_types: ClassVar[tuple[str, ...]] = ("dtc",)

    def __init__(self, settings: Settings, source: SourceConfig | None = None):
        self.settings = settings
        self.source = source or settings.source(self.slug)
        self.root: Path = self.source.local_path

    # -- lifecycle ---------------------------------------------------------
    def require_root(self) -> Path:
        if not self.root.is_dir():
            raise ConnectorError(
                f"{self.slug}: source checkout not found at {self.root}. "
                f"Run `autodoctor fetch-sources --source {self.slug}` first."
            )
        return self.root

    def version_info(self) -> VersionInfo:
        """Commit/label/dirty state. Overridden by multi-repository sources."""
        from ..utils.gitinfo import commit_sha, describe, is_dirty

        root = self.require_root()
        return VersionInfo(
            commit=commit_sha(root),
            label=describe(root),
            dirty=is_dirty(root),
        )

    @abc.abstractmethod
    def inspect(self) -> SourceInspection:
        """Describe the checkout: layout, counts, provenance metadata."""

    @abc.abstractmethod
    def extract(self) -> Iterator[RawRecord]:
        """Yield upstream records verbatim."""

    @abc.abstractmethod
    def normalize(self, raw: RawRecord, provenance_base: dict[str, Any]) -> Iterable[NormalizedRecord]:
        """Map a raw record into zero or more normalized records."""

    # -- helpers -----------------------------------------------------------
    def licence_dict(self) -> dict[str, Any]:
        lic = self.source.licence
        return {
            "code": lic.code,
            "data": lic.data,
            "data_url": lic.data_url,
            "contents": lic.contents,
            "attribution_required": lic.attribution_required,
            "share_alike": lic.share_alike,
            "redistribution_allowed": lic.redistribution_allowed,
            "commercial_use_allowed": lic.commercial_use_allowed,
            "legal_review": lic.legal_review,
        }

    def provenance_base(self, record: RawRecord, commit: str, ingested_at: str | None = None) -> dict[str, Any]:
        return {
            "source_slug": self.slug,
            "source_commit": record.extra.get("repo_commit") or commit,
            "file_path": record.file_path,
            "source_record_id": record.source_record_id,
            "raw_hash": record.payload_hash(),
            "extraction_method": f"{self.slug}_connector_v1",
            "ingested_at": ingested_at or utc_now(),
        }
