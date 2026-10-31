"""Project configuration: source registry and filesystem layout."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


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

    def database_path(self) -> Path:
        env = os.environ.get("AUTODOCTOR_DB")
        return Path(env).expanduser().resolve() if env else self.paths.database
