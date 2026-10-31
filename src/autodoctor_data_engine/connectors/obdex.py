"""Connector for foerbsnavi/OBDex.

Layout (observed at commit a9d0220):
    data/generic/{P0,P2,P3,U0,U3,B0,C0}xxx_enriched.yaml   list of DTC entries
    data/pids/mode01.yaml, mode09.yaml                     list of PID entries
    schema/code.schema.json, schema/pid.schema.json        JSON Schema
    LICENSE-DATA (CC0-1.0), LICENSE-CODE (MIT)

The files carry bilingual (en/de) titles, descriptions, causes with likelihood,
symptoms, repair estimates, MIL/emissions/limp-mode flags, related codes and
per-code source URLs. All of that is preserved; nothing is collapsed into one
description string.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from ..models import (
    Cause,
    Component,
    Context,
    Definition,
    Flags,
    NormalizedDtc,
    NormalizedPid,
    NormalizedRecord,
    Provenance,
    Repair,
    Symptom,
)
from ..normalizers.codes import code_category, infer_standard, normalize_code, normalize_related_code
from ..normalizers.keys import slug_key
from ..normalizers.manufacturers import canonical_manufacturer
from ..normalizers.text import clean_text, normalize_language, normalize_url
from ..parsers.json_loader import load_json
from ..parsers.yaml_loader import load_yaml
from ..utils.gitinfo import commit_sha, describe, is_dirty
from .base import RawRecord, SourceConnector, SourceInspection

_LIKELIHOODS = {"low", "medium", "high"}
_DIFFICULTIES = {"easy", "medium", "hard", "shop_only"}


def _as_dict(value: Any) -> dict[str, str]:
    """Normalize a `{en: ..., de: ...}` mapping to two-letter language keys."""
    if isinstance(value, str):
        return {"en": value}
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for lang, text in value.items():
        cleaned = clean_text(text)
        if cleaned:
            out[normalize_language(str(lang))] = cleaned
    return out


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class ObdexConnector(SourceConnector):
    slug = "obdex"
    record_types = ("dtc", "pid")

    # -- inspection --------------------------------------------------------
    def _dtc_files(self) -> list[Path]:
        return sorted((self.root / "data" / "generic").glob("*.yaml"))

    def _pid_files(self) -> list[Path]:
        return sorted((self.root / "data" / "pids").glob("*.yaml"))

    def inspect(self) -> SourceInspection:
        root = self.require_root()
        dtc_files = self._dtc_files()
        pid_files = self._pid_files()
        warnings: list[str] = []
        entries = 0
        for path in dtc_files:
            data = load_yaml(path) or []
            if not isinstance(data, list):
                warnings.append(f"{path.name}: expected a list, got {type(data).__name__}")
                continue
            entries += len(data)
        if not dtc_files:
            warnings.append("no data/generic/*.yaml files found")
        schema = root / "schema" / "code.schema.json"
        if schema.is_file():
            load_json(schema)  # fail fast on a corrupt schema
        layout = {
            "format": "yaml (list of DTC objects) + json schema + yaml pids",
            "dtc_files": [p.name for p in dtc_files],
            "dtc_entries": entries,
            "pid_files": [p.name for p in pid_files],
            "bilingual": ["en", "de"],
            "has_manufacturer_specific": False,
            "record_types": ["dtc", "pid"],
        }
        total = sum(p.stat().st_size for p in [*dtc_files, *pid_files])
        return SourceInspection(
            slug=self.slug,
            name=self.source.name,
            repo_url=self.source.repo_url,
            local_path=str(root),
            present=True,
            commit_sha=commit_sha(root),
            describe=describe(root),
            dirty=is_dirty(root),
            file_count=len(dtc_files) + len(pid_files),
            total_bytes=total,
            layout=layout,
            licence=self.licence_dict(),
            notes=self.source.notes,
            warnings=warnings,
        )

    # -- extraction --------------------------------------------------------
    def extract(self) -> Iterator[RawRecord]:
        for path in self._dtc_files():
            data = load_yaml(path) or []
            for index, entry in enumerate(data):
                if not isinstance(entry, dict) or not entry.get("code"):
                    continue
                code = normalize_code(entry["code"])
                yield RawRecord(
                    record_type="dtc",
                    source_record_id=f"{path.name}#{code}",
                    file_path=f"data/generic/{path.name}",
                    payload=entry,
                    extra={"file_index": index, "schema": "code.schema.json"},
                )
        for path in self._pid_files():
            data = load_yaml(path) or []
            for index, entry in enumerate(data):
                if not isinstance(entry, dict) or entry.get("pid") is None:
                    continue
                mode = str(entry.get("mode") or "").strip()
                pid = str(entry.get("pid")).strip().upper()
                yield RawRecord(
                    record_type="pid",
                    source_record_id=f"mode{mode}.{pid}",
                    file_path=f"data/pids/{path.name}",
                    payload=entry,
                    extra={"file_index": index, "schema": "pid.schema.json"},
                )

    # -- normalization -----------------------------------------------------
    def normalize(self, raw: RawRecord, provenance_base: dict[str, Any]) -> Iterable[NormalizedRecord]:
        prov = Provenance(**provenance_base)
        if raw.record_type == "dtc":
            record = self._normalize_dtc(raw, prov)
            return [record] if record else []
        return [self._normalize_pid(raw, prov)]

    def _normalize_dtc(self, raw: RawRecord, prov: Provenance) -> NormalizedDtc | None:
        payload = raw.payload
        code = normalize_code(payload.get("code"))
        if not code:
            return None

        definitions: list[Definition] = []
        titles, descriptions = _as_dict(payload.get("title")), _as_dict(payload.get("description"))
        for lang in sorted(set(titles) | set(descriptions)):
            definitions.append(
                Definition(
                    language=lang,
                    title=titles.get(lang),
                    description=descriptions.get(lang),
                )
            )

        causes = []
        for cause in payload.get("common_causes") or []:
            if not isinstance(cause, dict):
                continue
            labels = _as_dict(cause.get("label"))
            key = cause.get("id") or (labels.get("en") or labels.get("de") or "")
            likelihood = str(cause.get("likelihood") or "").lower()
            causes.append(
                Cause(
                    key=slug_key(str(key)),
                    likelihood=likelihood if likelihood in _LIKELIHOODS else None,  # type: ignore[arg-type]
                    labels=labels,
                )
            )

        symptoms = []
        for symptom in payload.get("symptoms") or []:
            texts = _as_dict(symptom)
            if not texts:
                continue
            anchor = texts.get("en") or next(iter(texts.values()))
            symptoms.append(Symptom(key=slug_key(anchor), texts=texts))

        repair_payload = payload.get("repair") or {}
        repairs = []
        if isinstance(repair_payload, dict) and repair_payload:
            cost = repair_payload.get("estimated_cost_eur") or []
            hours = repair_payload.get("estimated_hours") or []
            difficulty = str(repair_payload.get("difficulty") or "").lower()
            repairs.append(
                Repair(
                    key="repair_estimate",
                    texts={},
                    difficulty=difficulty if difficulty in _DIFFICULTIES else None,  # type: ignore[arg-type]
                    diy_possible=repair_payload.get("diy_possible"),
                    cost_min=_number(cost[0]) if isinstance(cost, list) and len(cost) == 2 else None,
                    cost_max=_number(cost[1]) if isinstance(cost, list) and len(cost) == 2 else None,
                    currency="EUR" if isinstance(cost, list) and cost else None,
                    hours_min=_number(hours[0]) if isinstance(hours, list) and len(hours) == 2 else None,
                    hours_max=_number(hours[1]) if isinstance(hours, list) and len(hours) == 2 else None,
                )
            )

        components = [
            Component(key=slug_key(str(comp)), labels={})
            for comp in (payload.get("affected_components") or [])
            if comp
        ]

        references = [str(ref) for ref in (payload.get("references") or []) if ref]
        evidence_urls = [
            url for url in (normalize_url(u) for u in (payload.get("sources") or []) if u) if url
        ]

        flags_payload = payload.get("flags") or {}
        flags = Flags(
            mil=flags_payload.get("mil"),
            emissions_relevant=flags_payload.get("emissions_relevant"),
            drive_cycle_required=flags_payload.get("drive_cycle_required"),
            limp_mode_possible=flags_payload.get("limp_mode_possible"),
        )

        # OBDex is a generic-layer source: SAE J2012 / ISO 15031-6 semantics only.
        declared_standard = None
        for ref in references:
            lower = ref.lower()
            if "j2012" in lower or "15031" in lower:
                declared_standard = "sae_j2012"
                break

        return NormalizedDtc(
            code=code,
            standard=infer_standard(code, declared=declared_standard, manufacturer_specific=False),
            protocol="obd2",
            category=clean_text(payload.get("category")) or code_category(code),
            context=Context(type="generic"),
            definitions=definitions,
            causes=causes,
            symptoms=symptoms,
            repairs=repairs,
            components=components,
            related_codes=[
                c for c in (normalize_related_code(v) for v in (payload.get("related_codes") or [])) if c
            ],
            flags=flags,
            references=references,
            evidence_urls=evidence_urls,
            provenance=prov,
        )

    def _normalize_pid(self, raw: RawRecord, prov: Provenance) -> NormalizedPid:
        payload = raw.payload
        rng = payload.get("range") or []
        return NormalizedPid(
            mode=str(payload.get("mode") or "").zfill(2),
            pid=str(payload.get("pid") or "").upper(),
            scope="generic",
            bytes=int(payload["bytes"]) if isinstance(payload.get("bytes"), int) else None,
            unit=clean_text(payload.get("unit")),
            formula=clean_text(payload.get("formula")),
            range_min=_number(rng[0]) if isinstance(rng, list) and len(rng) == 2 else None,
            range_max=_number(rng[1]) if isinstance(rng, list) and len(rng) == 2 else None,
            names=_as_dict(payload.get("name")),
            provenance=prov,
        )

    # -- supplementary metadata -------------------------------------------
    def coverage(self) -> dict[str, Any]:
        """Codes that are declared but not described cannot exist upstream (schema enforced)."""
        return {"empty_definition_allowed": False}

    def manufacturer_hint(self) -> None:
        """OBDex is generic-only; kept for symmetry with other connectors."""
        canonical_manufacturer(None)
