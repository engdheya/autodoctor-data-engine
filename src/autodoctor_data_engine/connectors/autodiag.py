"""Connector for autodiag2/database.

Layout (observed at commit 11e73fd):
    data-src/ecu/generic/<brand>/codes/<CODE>.yml      brand context
    data-src/ecu/generic/saej2012.2002/codes/*.yml     generic standard context
    data-src/ecu/<vendor>/<ecu_model>/codes/<CODE>.yml ECU context
    data-src/vehicle/<Make>/<Model>/...                vehicle / engine / ECU metadata
    manager/                                           GPL tooling (not imported)

28,833 code files, 16,674 unique codes. The YAML schema is uniform:
code, system, subsystem, category, definition, description, severity, mil,
related_code, detection_condition, causes, repairs, evidence, protocol, standard.

Almost all records only populate `definition`; causes/repairs/detection_condition
are present but empty. The value of this source is therefore *context*: it tells
us that P1641 means something for Audi generic, that a code is ECU specific, and
which protocol/standard applies - without inventing content.

Licence: data ODbL-1.0 (share-alike), code GPL-3.0-or-later. The compiled data is
marked pending in the registry until a legal review decides how to distribute it.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from ..models import (
    Cause,
    Context,
    Definition,
    Flags,
    NormalizedDtc,
    NormalizedEcu,
    NormalizedRecord,
    NormalizedVehicle,
    Provenance,
    Test,
)
from ..normalizers.codes import code_category, infer_standard, normalize_code, normalize_related_code
from ..normalizers.keys import slug_key
from ..normalizers.manufacturers import canonical_manufacturer
from ..normalizers.text import clean_text, normalize_url
from ..parsers.yaml_loader import load_yaml
from ..utils.gitinfo import commit_sha, describe, is_dirty
from .base import RawRecord, SourceConnector, SourceInspection

_STANDARD_MAP = {
    "saej2012.2002": "sae_j2012",
    "saej2012": "sae_j2012",
    "iso15031-6": "iso_15031_6",
}
_PROTOCOL_MAP = {"obd2": "obd2", "obd": "obd2", "uds": "uds", "can": "can"}


class AutodiagConnector(SourceConnector):
    slug = "autodiag"
    record_types = ("dtc", "ecu", "vehicle")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ecu_meta: dict[Path, dict[str, Any]] | None = None

    # -- discovery ---------------------------------------------------------
    @property
    def ecu_root(self) -> Path:
        return self.root / "data-src" / "ecu"

    def code_files(self) -> list[Path]:
        root = self.require_root() / "data-src"
        return sorted(root.glob("ecu/**/codes/*.yml"))

    def ecu_metadata(self) -> dict[Path, dict[str, Any]]:
        """Map an ECU directory to its def.yml metadata (model, type, mcu...)."""
        if self._ecu_meta is None:
            meta: dict[Path, dict[str, Any]] = {}
            for def_file in sorted(self.ecu_root.glob("**/def.yml")):
                try:
                    data = load_yaml(def_file) or {}
                except Exception:  # noqa: BLE001 - a broken def.yml must not kill the import
                    data = {}
                meta[def_file.parent] = data if isinstance(data, dict) else {}
            self._ecu_meta = meta
        return self._ecu_meta

    # -- inspection --------------------------------------------------------
    def inspect(self) -> SourceInspection:
        root = self.require_root()
        files = self.code_files()
        if not files:
            from .base import ConnectorError

            raise ConnectorError(f"{self.slug}: no code files under {self.ecu_root}")

        by_context: dict[str, int] = {}
        standards: dict[str, int] = {}
        protocols: dict[str, int] = {}
        filled = {"definition": 0, "description": 0, "causes": 0, "repairs": 0,
                  "detection_condition": 0}
        diagnostics = {"empty_definition": 0, "unparsable_yaml": 0, "missing_code_field": 0}
        codes: set[str] = set()
        total = 0
        base = root / "data-src" / "ecu"

        # single pass: every file is parsed exactly once (28k files, ~20s)
        for path in files:
            total += path.stat().st_size
            try:
                data = load_yaml(path)
            except Exception:  # noqa: BLE001
                diagnostics["unparsable_yaml"] += 1
                continue
            if not isinstance(data, dict):
                diagnostics["unparsable_yaml"] += 1
                continue
            if not data.get("code"):
                diagnostics["missing_code_field"] += 1
            if not (data.get("definition") or data.get("description")):
                diagnostics["empty_definition"] += 1
            code = normalize_code(data.get("code"))
            if code:
                codes.add(code)
            parts = path.relative_to(base).parts
            head = parts[0] if parts else "?"
            by_context[head] = by_context.get(head, 0) + 1
            for value in data.get("standard") or []:
                standards[str(value)] = standards.get(str(value), 0) + 1
            for value in data.get("protocol") or []:
                protocols[str(value)] = protocols.get(str(value), 0) + 1
            for field in filled:
                if data.get(field):
                    filled[field] += 1

        vehicle_files = sorted((root / "data-src" / "vehicle").glob("*/*/def.yml"))
        warnings = []
        if diagnostics["empty_definition"]:
            warnings.append(f"{diagnostics['empty_definition']} code files have no definition text")
        if diagnostics["unparsable_yaml"]:
            warnings.append(f"{diagnostics['unparsable_yaml']} code files could not be parsed as YAML")
        if diagnostics["missing_code_field"]:
            warnings.append(f"{diagnostics['missing_code_field']} code files have no `code` field")

        layout = {
            "format": "yaml, one file per (code, context)",
            "code_files": len(files),
            "unique_codes": len(codes),
            "contexts_top_level": dict(sorted(by_context.items(), key=lambda kv: -kv[1])),
            "standards": standards,
            "protocols": protocols,
            "populated_fields": filled,
            "vehicle_metadata_files": len(vehicle_files),
            "ecu_definitions": len(self.ecu_metadata()),
            "record_types": ["dtc", "ecu", "vehicle"],
            "diagnostics": diagnostics,
        }
        return SourceInspection(
            slug=self.slug,
            name=self.source.name,
            repo_url=self.source.repo_url,
            local_path=str(root),
            present=True,
            commit_sha=commit_sha(root),
            describe=describe(root),
            dirty=is_dirty(root),
            file_count=len(files),
            total_bytes=total,
            layout=layout,
            licence=self.licence_dict(),
            notes=self.source.notes,
            warnings=warnings,
        )

    def _diagnose(self, files: list[Path]) -> dict[str, int]:
        """Kept for targeted diagnostics; `inspect` performs a single pass itself."""
        counts = {"empty_definition": 0, "unparsable_yaml": 0, "missing_code_field": 0}
        for path in files:
            try:
                data = load_yaml(path)
            except Exception:  # noqa: BLE001
                counts["unparsable_yaml"] += 1
                continue
            if not isinstance(data, dict):
                counts["unparsable_yaml"] += 1
                continue
            if not data.get("code"):
                counts["missing_code_field"] += 1
            if not (data.get("definition") or data.get("description")):
                counts["empty_definition"] += 1
        return counts

    # -- extraction --------------------------------------------------------
    def extract(self) -> Iterator[RawRecord]:
        base = self.require_root() / "data-src" / "ecu"
        meta = self.ecu_metadata()
        for path in self.code_files():
            data = load_yaml(path)
            if not isinstance(data, dict):
                continue
            relative = path.relative_to(self.root).as_posix()
            parts = path.relative_to(base).parts
            yield RawRecord(
                record_type="dtc",
                source_record_id=relative,
                file_path=relative,
                payload=data,
                extra={"path_parts": list(parts), "ecu_meta": meta.get(path.parent.parent, {})},
            )

        # ECU entities (metadata only, no DTC relationship is invented)
        for ecu_dir, data in sorted(meta.items()):
            if data.get("type") in (None, "any"):
                continue
            relative = (ecu_dir / "def.yml").relative_to(self.root).as_posix()
            yield RawRecord(
                record_type="ecu",
                source_record_id=f"{relative}",
                file_path=relative,
                payload=data,
                extra={"vendor": ecu_dir.parent.name, "dir": ecu_dir.name},
            )

        # Vehicle entities
        for def_file in sorted((self.root / "data-src" / "vehicle").glob("*/*/def.yml")):
            data = load_yaml(def_file) or {}
            if not isinstance(data, dict):
                continue
            relative = def_file.relative_to(self.root).as_posix()
            yield RawRecord(
                record_type="vehicle",
                source_record_id=relative,
                file_path=relative,
                payload=data,
                extra={"manufacturer_dir": def_file.parent.parent.name, "model_dir": def_file.parent.name},
            )

    # -- normalization -----------------------------------------------------
    def normalize(self, raw: RawRecord, provenance_base: dict[str, Any]) -> Iterable[NormalizedRecord]:
        prov = Provenance(**provenance_base)
        if raw.record_type == "dtc":
            record = self._normalize_dtc(raw, prov)
            return [record] if record else []
        if raw.record_type == "ecu":
            return [self._normalize_ecu(raw, prov)]
        if raw.record_type == "vehicle":
            return [self._normalize_vehicle(raw, prov)]
        return []

    def _context_for(self, raw: RawRecord) -> Context:
        parts = list(raw.extra.get("path_parts") or [])
        # parts = [context_dir, entity, "codes", filename]
        if len(parts) < 3:
            return Context(type="generic")
        head, entity = parts[0], parts[1]
        if head == "generic":
            if entity.lower().startswith("sae") or entity.lower().startswith("iso"):
                return Context(type="generic")
            manufacturer = canonical_manufacturer(entity)
            if manufacturer:
                return Context(type="manufacturer", manufacturer=manufacturer)
            return Context(type="generic")
        meta = raw.extra.get("ecu_meta") or {}
        model = clean_text(meta.get("model")) or entity
        ecu_name = f"{head.replace('_', ' ').title()} {model}"
        return Context(type="ecu", ecu=ecu_name)

    def _normalize_dtc(self, raw: RawRecord, prov: Provenance) -> NormalizedDtc | None:
        payload = raw.payload
        code = normalize_code(payload.get("code"))
        if not code:
            return None

        definition = clean_text(payload.get("definition"))
        description = clean_text(payload.get("description"))
        definitions = []
        if definition or description:
            definitions.append(
                Definition(language="en", title=definition, description=description)
            )

        declared_standard = None
        for value in payload.get("standard") or []:
            key = str(value).strip().lower()
            declared_standard = _STANDARD_MAP.get(key, key)
            break
        protocols = [str(p).strip().lower() for p in (payload.get("protocol") or [])]
        protocol = _PROTOCOL_MAP.get(protocols[0], protocols[0]) if protocols else None

        contexts = self._context_for(raw)
        manufacturer_specific = contexts.type != "generic"

        causes = []
        for index, cause in enumerate(payload.get("causes") or []):
            if isinstance(cause, dict):
                label = clean_text(cause.get("en") or cause.get("label") or cause.get("text"))
                likelihood = str(cause.get("likelihood") or "").lower()
                key = cause.get("id") or label or f"cause_{index}"
            else:
                label = clean_text(cause)
                likelihood = ""
                key = label or f"cause_{index}"
            if not label:
                continue
            causes.append(
                Cause(
                    key=slug_key(str(key)),
                    likelihood=likelihood if likelihood in {"low", "medium", "high"} else None,  # type: ignore[arg-type]
                    labels={"en": label},
                )
            )

        tests = []
        for index, condition in enumerate(payload.get("detection_condition") or []):
            text = clean_text(condition if isinstance(condition, str) else str(condition))
            if text:
                tests.append(Test(key=f"detection_condition_{index}", kind="check", texts={"en": text}))

        related = [
            c for c in (normalize_related_code(v) for v in (payload.get("related_code") or [])) if c
        ]

        evidence_urls: list[str] = []
        references: list[str] = []
        for item in payload.get("evidence") or []:
            value = clean_text(item)
            if not value:
                continue
            url = normalize_url(value)
            if url and url.startswith("http"):
                evidence_urls.append(url)
            else:
                references.append(value)

        return NormalizedDtc(
            code=code,
            standard=infer_standard(code, declared=declared_standard, manufacturer_specific=manufacturer_specific),
            protocol=protocol,
            category=clean_text(payload.get("category")) or code_category(code),
            system=clean_text(payload.get("system")),
            subsystem=clean_text(payload.get("subsystem")),
            context=contexts,
            definitions=definitions,
            causes=causes,
            tests=tests,
            related_codes=related,
            flags=Flags(
                mil=None if payload.get("mil") in ("", None) else bool(payload.get("mil")),
                severity_label=clean_text(payload.get("severity")),
            ),
            references=references,
            evidence_urls=evidence_urls,
            provenance=prov,
        )

    def _normalize_ecu(self, raw: RawRecord, prov: Provenance) -> NormalizedEcu:
        payload = raw.payload
        vendor_raw = raw.extra.get("vendor") or ""
        model = clean_text(payload.get("model")) or raw.extra.get("dir") or "unknown"
        vendor = vendor_raw.replace("_", " ").title() if vendor_raw else None
        return NormalizedEcu(
            name=f"{vendor} {model}".strip() if vendor else model,
            vendor=vendor,
            model=model,
            ecu_type=clean_text(payload.get("type")),
            protocol="uds" if "uds" in str(payload.get("type", "")).lower() else None,
            provenance=prov,
        )

    def _normalize_vehicle(self, raw: RawRecord, prov: Provenance) -> NormalizedVehicle:
        payload = raw.payload
        manufacturer_dir = raw.extra.get("manufacturer_dir") or ""
        manufacturer = canonical_manufacturer(manufacturer_dir) or manufacturer_dir.replace("_", " ")
        model = clean_text(payload.get("model")) or (raw.extra.get("model_dir") or "unknown").replace("_", " ")
        return NormalizedVehicle(
            manufacturer=manufacturer,
            model=model,
            provenance=prov,
        )
