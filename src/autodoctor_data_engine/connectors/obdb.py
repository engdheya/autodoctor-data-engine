"""Connector for the OBDb organisation (one repository per vehicle).

Layout (observed at Porsche/Toyota/Nissan repositories, 2026-10):
    <repo>/signalsets/v3/default.json   {"ecu": [...], "commands": [...]}
    <repo>/generations.yaml             model generations with year ranges
    <repo>/tests/test_cases/...         recorded ISO-TP responses (not imported)
    <repo>/LICENSE                      CC-BY-SA-4.0

There are **no DTC definitions** in OBDb. It is a vehicle/ECU/parameter source:
which CAN header carries which ECU, which Mode 21/22 parameters exist, and which
model years each signal applies to. The engine therefore never creates a DTC from
this source and never links a DTC to a vehicle unless another source documents it.

Because the organisation is a collection of repositories, ``local_path`` points at
a directory containing the clones (``vendor/upstream/OBDb/<Repo>``). A single
checkout is also accepted.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from ..models import (
    Context,
    NormalizedEcu,
    NormalizedPid,
    NormalizedRecord,
    NormalizedVehicle,
    Provenance,
)
from ..normalizers.manufacturers import ALIASES
from ..normalizers.text import clean_text
from ..parsers.json_loader import load_json
from ..parsers.yaml_loader import load_yaml
from ..utils.gitinfo import commit_sha, is_dirty
from ..utils.hashing import sha256_json
from .base import RawRecord, SourceConnector, SourceInspection, VersionInfo


def split_repo_name(name: str) -> tuple[str, str]:
    """Split "Mercedes-Benz-EQS-Class-Sedan" into ("Mercedes-Benz", "EQS-Class-Sedan").

    The organisation encodes manufacturer and model in the repository name with a
    hyphen, and both sides may contain hyphens. We therefore try the longest
    prefix that is a known manufacturer alias before falling back to the first
    token.
    """
    parts = name.split("-")
    for index in range(len(parts) - 1, 0, -1):
        candidate = "-".join(parts[:index])
        if candidate.upper() in ALIASES:
            return ALIASES[candidate.upper()], "-".join(parts[index:])
    if len(parts) > 1:
        return parts[0], "-".join(parts[1:])
    return name, "unknown"


class ObdbConnector(SourceConnector):
    slug = "obdb"
    record_types = ("vehicle", "ecu", "pid")

    # -- discovery ---------------------------------------------------------
    def vehicle_repos(self) -> list[Path]:
        root = self.require_root()
        if (root / "signalsets").is_dir() or (root / "generations.yaml").is_file():
            return [root]
        repos = []
        for child in sorted(root.iterdir()):
            if child.is_dir() and not child.name.startswith(".") and (
                (child / "signalsets").is_dir() or (child / "generations.yaml").is_file()
            ):
                repos.append(child)
        return repos

    def _signalset(self, repo: Path) -> dict[str, Any]:
        path = repo / "signalsets" / "v3" / "default.json"
        if not path.is_file():
            candidates = sorted((repo / "signalsets").glob("**/*.json"))
            if not candidates:
                return {}
            path = candidates[0]
        data = load_json(path)
        return data if isinstance(data, dict) else {}

    def _generations(self, repo: Path) -> list[dict[str, Any]]:
        path = repo / "generations.yaml"
        if not path.is_file():
            return []
        data = load_yaml(path) or {}
        generations = data.get("generations") if isinstance(data, dict) else None
        return [g for g in (generations or []) if isinstance(g, dict)]

    def repo_commits(self) -> dict[str, str | None]:
        return {repo.name: commit_sha(repo) for repo in self.vehicle_repos()}

    def version_info(self) -> VersionInfo:
        """OBDb is an organisation, so the version is the set of repository commits."""
        commits = self.repo_commits()
        synthetic = f"obdb:{sha256_json(commits)[:32]}"
        dirty = any(is_dirty(repo) for repo in self.vehicle_repos())
        return VersionInfo(
            commit=synthetic,
            label=f"{len(commits)} vehicle repositories",
            dirty=dirty,
            warnings=[],
            extra={"repo_commits": commits},
        )

    # -- inspection --------------------------------------------------------
    def inspect(self) -> SourceInspection:
        root = self.require_root()
        repos = self.vehicle_repos()
        if not repos:
            from .base import ConnectorError

            raise ConnectorError(
                f"{self.slug}: no OBDb vehicle repositories under {root}. "
                "Run `autodoctor fetch-sources --source obdb` first."
            )
        dct_terms, dtc_files = 0, 0
        signals = 0
        ecus = 0
        years: set[int] = set()
        warnings: list[str] = []
        per_repo = {}
        file_count = 0
        total_bytes = 0
        repo_commits: dict[str, str | None] = {}
        for repo in repos:
            repo_commits[repo.name] = commit_sha(repo)
            file_count += sum(1 for item in repo.rglob("*") if item.is_file())
            total_bytes += sum(item.stat().st_size for item in repo.rglob("*") if item.is_file())
            data = self._signalset(repo)
            ecu_list = data.get("ecu") or []
            commands = data.get("commands") or []
            repo_signals = sum(len(c.get("signals") or []) for c in commands if isinstance(c, dict))
            signals += repo_signals
            ecus += len(ecu_list)
            gens = self._generations(repo)
            for gen in gens:
                for key in ("start_year", "end_year"):
                    if isinstance(gen.get(key), int):
                        years.add(gen[key])
            dtc_dir = repo / "dtc"
            if dtc_dir.is_dir():
                dtc_files += sum(1 for _ in dtc_dir.rglob("*"))
            dct_terms += 1 if any("dtc" in str(s.get("path", "")).lower()
                                  for c in commands if isinstance(c, dict)
                                  for s in (c.get("signals") or []) if isinstance(s, dict)) else 0
            per_repo[repo.name] = {
                "commit": repo_commits[repo.name],
                "ecus": len(ecu_list),
                "commands": len(commands),
                "signals": repo_signals,
                "generations": len(gens),
            }
        if dtc_files:
            warnings.append(
                f"{dtc_files} files in dtc/ directories were found; the connector does not "
                "import DTC definitions from OBDb yet"
            )
        if not any(per_repo.values()):
            warnings.append("no signalsets could be parsed")

        layout = {
            "format": "json signalsets + yaml generations, one repository per vehicle",
            "repositories": len(repos),
            "repo_commits": repo_commits,
            "signals": signals,
            "ecu_entries": ecus,
            "model_year_span": [min(years), max(years)] if years else None,
            "dtc_definitions": 0,
            "repos_with_dtc_paths": dct_terms,
            "record_types": ["vehicle", "ecu", "pid"],
            "detail": per_repo,
        }
        return SourceInspection(
            slug=self.slug,
            name=self.source.name,
            repo_url=self.source.repo_url,
            local_path=str(root),
            present=True,
            commit_sha=f"obdb:{sha256_json(repo_commits)[:32]}",
            describe=f"{len(repos)} vehicle repositories",
            dirty=any(is_dirty(repo) for repo in repos),
            file_count=file_count,
            total_bytes=total_bytes,
            layout=layout,
            licence=self.licence_dict(),
            notes=self.source.notes,
            warnings=warnings,
        )

    # -- extraction --------------------------------------------------------
    def extract(self) -> Iterator[RawRecord]:
        repo_commits = self.repo_commits()
        for repo in self.vehicle_repos():
            manufacturer, model = split_repo_name(repo.name)
            relative_repo = repo.relative_to(self.root).as_posix() if repo != self.root else "."
            generations = self._generations(repo)
            if generations:
                for index, generation in enumerate(generations):
                    yield RawRecord(
                        record_type="vehicle",
                        source_record_id=f"{repo.name}#generation#{index}",
                        file_path=f"{relative_repo}/generations.yaml",
                        payload=generation,
                        extra={"manufacturer": manufacturer, "model": model, "repo": repo.name,
                               "index": index, "repo_commit": repo_commits.get(repo.name)},
                    )
            else:
                yield RawRecord(
                    record_type="vehicle",
                    source_record_id=f"{repo.name}#root",
                    file_path=f"{relative_repo}/README.md",
                    payload={"model": model},
                    extra={"manufacturer": manufacturer, "model": model, "repo": repo.name,
                           "index": 0},
                )

            signalset = self._signalset(repo)
            for index, ecu in enumerate(signalset.get("ecu") or []):
                if not isinstance(ecu, dict):
                    continue
                yield RawRecord(
                    record_type="ecu",
                    source_record_id=f"{repo.name}#ecu#{ecu.get('hdr', index)}",
                    file_path=f"{relative_repo}/signalsets/v3/default.json",
                    payload=ecu,
                    extra={"manufacturer": manufacturer, "model": model, "repo": repo.name,
                           "index": index},
                )
            for cmd_index, command in enumerate(signalset.get("commands") or []):
                if not isinstance(command, dict):
                    continue
                for signal_index, signal in enumerate(command.get("signals") or []):
                    if not isinstance(signal, dict):
                        continue
                    yield RawRecord(
                        record_type="pid",
                        source_record_id=f"{repo.name}#{signal.get('id') or f'{cmd_index}.{signal_index}'}",
                        file_path=f"{relative_repo}/signalsets/v3/default.json",
                        payload={"signal": signal, "command": {
                            "hdr": command.get("hdr"), "rax": command.get("rax"),
                            "cmd": command.get("cmd"), "freq": command.get("freq"),
                        }},
                        extra={"manufacturer": manufacturer, "model": model, "repo": repo.name},
                    )

    # -- normalization -----------------------------------------------------
    def normalize(self, raw: RawRecord, provenance_base: dict[str, Any]) -> Iterable[NormalizedRecord]:
        prov = Provenance(**provenance_base)
        if raw.record_type == "vehicle":
            return [self._normalize_vehicle(raw, prov)]
        if raw.record_type == "ecu":
            return [self._normalize_ecu(raw, prov)]
        if raw.record_type == "pid":
            pid = self._normalize_parameter(raw, prov)
            return [pid] if pid else []
        return []

    def _normalize_vehicle(self, raw: RawRecord, prov: Provenance) -> NormalizedVehicle:
        payload = raw.payload
        generation = clean_text(payload.get("name"))
        return NormalizedVehicle(
            manufacturer=raw.extra["manufacturer"],
            model=raw.extra["model"],
            generation=generation,
            year_start=payload.get("start_year") if isinstance(payload.get("start_year"), int) else None,
            year_end=payload.get("end_year") if isinstance(payload.get("end_year"), int) else None,
            description=clean_text(payload.get("description")),
            variant_name=generation,
            provenance=prov,
        )

    def _normalize_ecu(self, raw: RawRecord, prov: Provenance) -> NormalizedEcu:
        payload = raw.payload
        header = str(payload.get("hdr") or "").upper() or None
        ecu_type = clean_text(payload.get("type"))
        name = " ".join(
            part for part in [raw.extra["manufacturer"], raw.extra["model"],
                              f"ECU {header}" if header else None] if part
        )
        return NormalizedEcu(
            name=name,
            vendor=None,
            model=raw.extra["model"],
            ecu_type=ecu_type,
            protocol="can",
            header=header,
            vehicle_variant=f"{raw.extra['manufacturer']} {raw.extra['model']}",
            provenance=prov,
        )

    def _normalize_parameter(self, raw: RawRecord, prov: Provenance) -> NormalizedPid | None:
        signal = raw.payload.get("signal") or {}
        command = raw.payload.get("command") or {}
        cmd = command.get("cmd") or {}
        if not isinstance(cmd, dict) or not cmd:
            return None
        mode = str(next(iter(cmd))).upper()
        pid = str(cmd[next(iter(cmd))]).upper()
        fmt = signal.get("fmt") if isinstance(signal.get("fmt"), dict) else {}
        unit = clean_text(fmt.get("unit")) if fmt else None
        name = clean_text(signal.get("name"))
        return NormalizedPid(
            mode=mode,
            pid=pid,
            scope="vehicle",
            unit=unit,
            signal_id=clean_text(signal.get("id")),
            path=clean_text(signal.get("path")),
            fmt=fmt or None,
            names={"en": name} if name else {},
            provenance=prov,
        )

    # -- helpers -----------------------------------------------------------
    def dtc_context(self) -> Context:
        """OBDb cannot provide a DTC context on its own; used by tests/documentation."""
        return Context(type="generic")
