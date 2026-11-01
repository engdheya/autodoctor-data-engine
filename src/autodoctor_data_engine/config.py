"""Project configuration: source registry and filesystem layout."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")

#: A build is either for our own use ("private") or for redistribution
#: ("public"). The public set only ever contains sources whose data licence
#: allows redistribution *and* whose legal review is approved.
SOURCE_SETS = ("private", "public")
DEFAULT_SOURCE_SET = "private"


class ConfigError(RuntimeError):
    """Raised when the source registry is missing or malformed."""


def _expand(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        name, default = match.group(1), match.group(2) or ""
        return os.environ.get(name, default)

    return _ENV_PATTERN.sub(repl, value)


def find_project_root(start: Path | None = None) -> Path:
    """Locate the repository root (the directory holding ``config/sources.yaml``)."""
    env = os.environ.get("AUTODOCTOR_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    candidates = []
    if start:
        candidates.append(start)
    candidates.append(Path.cwd())
    candidates.append(Path(__file__).resolve())
    for candidate in candidates:
        for parent in [candidate, *candidate.parents]:
            if (parent / "config" / "sources.yaml").is_file():
                return parent
    raise ConfigError(
        "could not locate config/sources.yaml - run the command from the project root "
        "or set AUTODOCTOR_ROOT"
    )


@dataclass(frozen=True)
class LicenceInfo:
    code: str | None = None
    data: str | None = None
    data_url: str | None = None
    contents: str | None = None
    attribution_required: bool = True
    share_alike: bool = False
    redistribution_allowed: bool | None = None
    commercial_use_allowed: bool | None = None
    legal_review: str = "pending"

    @property
    def blocking(self) -> bool:
        """True when data must not be shipped in a redistributable bundle."""
        return self.legal_review != "approved" or self.redistribution_allowed is False

    def reason(self) -> str:
        """Human readable why this source is (not) redistributable."""
        if self.redistribution_allowed is False:
            return "redistribution not allowed by the data licence"
        if self.legal_review == "approved":
            return "legal review approved"
        return f"legal review {self.legal_review}"


@dataclass(frozen=True)
class SourceConfig:
    slug: str
    name: str
    repo_url: str
    local_path: Path
    kind: str
    enabled: bool
    licence: LicenceInfo
    lineage: str
    import_scope: tuple[str, ...]
    notes: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def redistributable(self) -> bool:
        """True only when the data may legally leave this project."""
        return not self.licence.blocking

    def set_membership(self, source_set: str) -> bool:
        """Is this source part of the given delivery set?"""
        if source_set == "public":
            return self.redistributable
        if source_set == "private":
            return True
        raise ConfigError(
            f"unknown source set {source_set!r}; expected one of {', '.join(SOURCE_SETS)}"
        )


@dataclass(frozen=True)
class Paths:
    root: Path
    raw: Path
    staging: Path
    processed: Path
    exports: Path
    reports: Path
    upstream: Path
    db_dir: Path
    schema: Path
    database: Path

    def ensure(self) -> None:
        for path in (self.raw, self.staging, self.processed, self.exports, self.reports):
            path.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Rules:
    code_pattern: str
    uds_code_pattern: str
    similarity_threshold: float
    min_corroborating_lineages: int
    blocked_redistribution_review: tuple[str, ...]


class Settings:
    """Loaded registry + paths + rules."""

    def __init__(self, root: Path | None = None, config_path: Path | None = None):
        self.root = root or find_project_root()
        self.config_path = config_path or (self.root / "config" / "sources.yaml")
        if not self.config_path.is_file():
            raise ConfigError(f"source registry not found: {self.config_path}")
        with open(self.config_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        self.project: dict[str, Any] = data.get("project") or {}
        self._raw = data

        raw_paths = data.get("paths") or {}
        upstream = self._resolve_path(raw_paths.get("upstream", "vendor/upstream"))
        self.paths = Paths(
            root=self.root,
            raw=self._resolve_path(raw_paths.get("raw", "data/raw")),
            staging=self._resolve_path(raw_paths.get("staging", "data/staging")),
            processed=self._resolve_path(raw_paths.get("processed", "data/processed")),
            exports=self._resolve_path(raw_paths.get("exports", "data/exports")),
            reports=self._resolve_path(raw_paths.get("reports", "data/reports")),
            upstream=upstream,
            db_dir=self.root / "db",
            schema=self.root / "db" / "schema.sql",
            database=self.root / "db" / self.project.get("database_filename", "autodoctor.sqlite"),
        )

        self.sources: dict[str, SourceConfig] = {}
        for entry in data.get("sources") or []:
            slug = entry["slug"]
            lic = entry.get("licence") or {}
            self.sources[slug] = SourceConfig(
                slug=slug,
                name=entry.get("name", slug),
                repo_url=entry.get("repo_url", ""),
                local_path=self._resolve_path(entry.get("local_path", f"vendor/upstream/{slug}")),
                kind=entry.get("kind", slug),
                enabled=bool(entry.get("enabled", True)),
                licence=LicenceInfo(
                    code=lic.get("code"),
                    data=lic.get("data"),
                    data_url=lic.get("data_url"),
                    contents=lic.get("contents_licence"),
                    attribution_required=bool(lic.get("attribution_required", True)),
                    share_alike=bool(lic.get("share_alike", False)),
                    redistribution_allowed=lic.get("redistribution_allowed"),
                    commercial_use_allowed=lic.get("commercial_use_allowed"),
                    legal_review=lic.get("legal_review", "pending"),
                ),
                lineage=entry.get("lineage", slug),
                import_scope=tuple(entry.get("import_scope") or ()),
                notes=(entry.get("notes") or "").strip(),
                raw=entry,
            )

        rules = data.get("rules") or {}
        self.rules = Rules(
            code_pattern=rules.get("code_pattern", r"^[PBCU][0-3][0-9A-F]{3}$"),
            uds_code_pattern=rules.get("uds_code_pattern", r"^[0-9A-F]{6,8}$"),
            similarity_threshold=float(rules.get("similarity_threshold", 0.85)),
            min_corroborating_lineages=int(rules.get("min_corroborating_lineages", 2)),
            blocked_redistribution_review=tuple(rules.get("blocked_redistribution_review") or ()),
        )

    def _resolve_path(self, value: str) -> Path:
        expanded = _expand(value)
        path = Path(expanded)
        return path if path.is_absolute() else (self.root / path).resolve()

    def source(self, slug: str) -> SourceConfig:
        try:
            return self.sources[slug]
        except KeyError as exc:
            raise ConfigError(
                f"unknown source {slug!r}; known sources: {', '.join(sorted(self.sources))}"
            ) from exc

    def enabled_sources(self) -> list[SourceConfig]:
        return [s for s in self.sources.values() if s.enabled]

    # -- source sets ----------------------------------------------------
    # A "source set" is the licence boundary of a build. Nothing else in the
    # codebase decides what may be published: every build, export and bundle
    # resolves its contents through these three methods.
    def source_set_slugs(self, source_set: str) -> list[str]:
        return [s.slug for s in self.enabled_sources() if s.set_membership(source_set)]

    def source_set_report(self, source_set: str) -> dict[str, list[dict[str, str]]]:
        included: list[dict[str, str]] = []
        excluded: list[dict[str, str]] = []
        for source in self.enabled_sources():
            entry = {
                "slug": source.slug,
                "data_license": source.licence.data or "unknown",
                "legal_review": source.licence.legal_review,
                "reason": source.licence.reason(),
            }
            (included if source.set_membership(source_set) else excluded).append(entry)
        return {"included": included, "excluded": excluded}

    def resolve_source_set(
        self, source_set: str, requested: list[str] | None = None
    ) -> tuple[list[str], dict[str, Any]]:
        """Resolve ``--source-set`` + ``--source`` into the slugs to import.

        Requesting a source that the set excludes is an error, never a silent
        downgrade: a public build must not be able to include autodiag2 because
        someone passed ``--source autodiag`` by habit.
        """
        if source_set not in SOURCE_SETS:
            raise ConfigError(
                f"unknown source set {source_set!r}; expected one of {', '.join(SOURCE_SETS)}"
            )
        allowed = self.source_set_slugs(source_set)
        if requested:
            blocked = [slug for slug in requested if slug not in allowed]
            if blocked:
                details = "; ".join(
                    f"{slug}: {self.source(slug).licence.reason()}" for slug in blocked
                )
                raise ConfigError(
                    f"source set {source_set!r} excludes {', '.join(blocked)} ({details}). "
                    "Build with --source-set private to include them."
                )
            allowed = [slug for slug in allowed if slug in requested]
        report = self.source_set_report(source_set)
        report["source_set"] = source_set
        return allowed, report

    def database_path(self) -> Path:
        env = os.environ.get("AUTODOCTOR_DB")
        return Path(env).expanduser().resolve() if env else self.paths.database
