"""Merge loader: normalized records -> unified SQLite database.

Guarantees
  * every inserted fact gets a provenance claim pointing at a source record
  * identifiers are never collapsed across contexts
  * a conflict never deletes data: both statements survive, both are flagged
  * canonical selection is deterministic (source precedence, then richness)
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..config import Settings
from ..conflict_resolution.detector import Conflict
from ..database.repository import Repository
from ..deduplication.detector import DuplicateGroup
from ..identity import definition_content_hash
from ..models import (
    NormalizedDtc,
    NormalizedEcu,
    NormalizedPid,
    NormalizedVehicle,
)
from ..normalizers.keys import humanize_key
from ..reviews import ReviewStore, conflict_fingerprint
from ..staging import SourceBundle
from ..utils.hashing import sha256_text

#: when two sources state the same thing, the richer/older source wins the
#: canonical slot. This is a display choice, not a truth claim.
SOURCE_PRECEDENCE = {"obdex": 0, "wal33d": 1, "autodiag": 2, "obdb": 3}

RISK_RULE_ID = "risk_flags_v1"


@dataclass
class LoadStats:
    sources: int = 0
    data_versions: int = 0
    source_files: int = 0
    source_records: int = 0
    manufacturers: int = 0
    ecus: int = 0
    vehicles: int = 0
    vehicle_variants: int = 0
    pids: int = 0
    dtc_codes: int = 0
    definitions: int = 0
    causes: int = 0
    symptoms: int = 0
    tests: int = 0
    repairs: int = 0
    components: int = 0
    related_codes: int = 0
    flags: int = 0
    claims: int = 0
    conflicts: int = 0
    conflicts_resolved: int = 0
    duplicate_groups: int = 0
    skipped: dict[str, int] = field(default_factory=dict)

    def record_skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "sources": self.sources,
            "data_versions": self.data_versions,
            "source_files": self.source_files,
            "source_records": self.source_records,
            "manufacturers": self.manufacturers,
            "ecus": self.ecus,
            "vehicles": self.vehicles,
            "vehicle_variants": self.vehicle_variants,
            "pids": self.pids,
            "dtc_codes": self.dtc_codes,
            "definitions": self.definitions,
            "causes": self.causes,
            "symptoms": self.symptoms,
            "tests": self.tests,
            "repairs": self.repairs,
            "components": self.components,
            "related_codes": self.related_codes,
            "flags": self.flags,
            "claims": self.claims,
            "conflicts": self.conflicts,
            "conflicts_resolved": self.conflicts_resolved,
            "duplicate_groups": self.duplicate_groups,
            "skipped": dict(sorted(self.skipped.items())),
        }


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class MergeLoader:
    def __init__(self, conn: sqlite3.Connection, settings: Settings, *, include_raw: bool = False):
        self.conn = conn
        self.settings = settings
        self.include_raw = include_raw
        self.repo = Repository(conn)
        self.stats = LoadStats()
        self.now = _now()
        self._source_record_ids: dict[str, int] = {}
        self._source_ids: dict[str, int] = {}
        self._version_ids: dict[str, int] = {}
        self._definitions: dict[tuple[int, str, str], int] = {}
        self._file_ids: dict[tuple[str, str], int] = {}
        self._priority_by_slug: dict[str, int] = {}
        self.review_stats: dict[str, int] = {"applied": 0, "canonical_overrides": 0, "unmatched": 0}

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def load(
        self,
        bundles: list[SourceBundle],
        conflicts: list[Conflict] | None = None,
        duplicate_groups: list[DuplicateGroup] | None = None,
        reviews: ReviewStore | None = None,
    ) -> LoadStats:
        conflicts = conflicts or []
        duplicate_groups = duplicate_groups or []

        bundles = sorted(
            bundles,
            key=lambda b: (SOURCE_PRECEDENCE.get(b.slug, 99), b.slug),
        )
        for bundle in bundles:
            self._priority_by_slug[bundle.slug] = SOURCE_PRECEDENCE.get(bundle.slug, 99)
            self._load_bundle_sources(bundle)

        with self.conn:  # single transaction
            for bundle in bundles:
                for record in bundle.records:
                    if isinstance(record, NormalizedDtc):
                        self._load_dtc(record, bundle)
                    elif isinstance(record, NormalizedPid):
                        self._load_pid(record, bundle)
                    elif isinstance(record, NormalizedVehicle):
                        self._load_vehicle(record, bundle)
                    elif isinstance(record, NormalizedEcu):
                        self._load_ecu(record, bundle)

            self._mark_conflicts(conflicts)
            self._set_canonical_and_verification()
            self.review_stats = self._apply_reviews(reviews)
            self._propagate_code_status()
            self._store_duplicate_groups(duplicate_groups)
            self._compute_risk()
            self.stats.dtc_codes = self._count("dtc_codes")
            self.stats.definitions = self._count("dtc_definitions")
            self.stats.manufacturers = self._count("manufacturers")
            self.stats.ecus = self._count("ecus")
            self.stats.pids = self._count("pids")
            self.stats.related_codes = self._count("dtc_related_codes")

        return self.stats

    # ------------------------------------------------------------------
    # sources / raw records
    # ------------------------------------------------------------------
    def _load_bundle_sources(self, bundle: SourceBundle) -> None:
        source = self.settings.source(bundle.slug)
        with self.conn:
            source_id = self.repo.upsert_source(source, self.now)
            self._source_ids[bundle.slug] = source_id
            version_id = self.repo.upsert_version(
                source_id=source_id,
                commit_sha=bundle.commit_sha,
                retrieved_at=bundle.retrieved_at,
                file_count=len(bundle.files),
                record_count=len(bundle.records),
                content_hash=bundle.content_hash,
                version_label=bundle.version_label,
            )
            self._version_ids[bundle.slug] = version_id
            self.stats.sources += 1
            self.stats.data_versions += 1

            counts_by_path: dict[str, int] = {}
            for record in bundle.records:
                counts_by_path[record.provenance.file_path] = (
                    counts_by_path.get(record.provenance.file_path, 0) + 1
                )

            for file_entry in bundle.files:
                path = file_entry.get("path")
                if not path:
                    continue
                file_id = self.repo.upsert_source_file(
                    version_id=version_id,
                    path=path,
                    sha256=file_entry.get("sha256", ""),
                    size_bytes=int(file_entry.get("size_bytes", 0)),
                    record_type=file_entry.get("record_type"),
                    record_count=counts_by_path.get(path, int(file_entry.get("record_count", 0))),
                )
                self._file_ids[(bundle.slug, path)] = file_id
                self.stats.source_files += 1

    def _source_record(self, record, bundle: SourceBundle) -> int:
        prov = record.provenance
        key = f"{bundle.slug}:{prov.source_record_id}"
        if key in self._source_record_ids:
            return self._source_record_ids[key]

        file_key = (bundle.slug, prov.file_path)
        file_id = self._file_ids.get(file_key)
        if file_id is None:
            file_id = self.repo.upsert_source_file(
                version_id=self._version_ids[bundle.slug],
                path=prov.file_path,
                sha256="",
                size_bytes=0,
                record_type=record.record_type,
                record_count=0,
            )
            self._file_ids[file_key] = file_id
            self.stats.source_files += 1

        raw_json = None
        if self.include_raw:
            raw_json = json.dumps({"source_record_id": prov.source_record_id}, ensure_ascii=False)

        record_id = self.repo.insert_source_record(
            source_file_id=file_id,
            source_record_id=prov.source_record_id,
            record_type=record.record_type,
            raw_hash=prov.raw_hash,
            raw_archive_path=bundle.raw_archive or "",
            ingested_at=prov.ingested_at,
            raw_json=raw_json,
        )
        self._source_record_ids[key] = record_id
        self.stats.source_records += 1
        return record_id

    def _claim(
        self,
        entity_type: str,
        entity_id: int,
        attribute: str,
        record,
        bundle: SourceBundle,
        source_record_id: int,
        value: Any,
        *,
        is_derived: bool = False,
        is_translated: bool = False,
        notes: str | None = None,
    ) -> int:
        claim_id = self.repo.add_claim(
            entity_type=entity_type,
            entity_id=entity_id,
            attribute=attribute,
            source_id=self._source_ids[bundle.slug],
            version_id=self._version_ids[bundle.slug],
            source_record_id=None if is_derived else source_record_id,
            # the claim's own value hash is derivable from source_records.raw_hash and
            # the entity content_hash; storing it per claim would add ~20 MB
            value_hash=None,
            extracted_at=record.provenance.ingested_at,
            extraction_method=record.provenance.extraction_method,
            is_derived=is_derived,
            is_translated=is_translated,
            notes=notes,
        )
        self.stats.claims += 1
        return claim_id

    # ------------------------------------------------------------------
    # DTC
    # ------------------------------------------------------------------
    def _load_dtc(self, record: NormalizedDtc, bundle: SourceBundle) -> None:
        source_record_id = self._source_record(record, bundle)

        manufacturer_id = None
        if record.context.manufacturer:
            manufacturer_id = self.repo.upsert_manufacturer(record.context.manufacturer)
            self.stats.manufacturers = len(self.repo._manufacturers)
        ecu_id = None
        if record.context.ecu:
            ecu_id = self.repo.upsert_ecu(name=record.context.ecu)
            self.stats.ecus = len(self.repo._ecus)

        code_id = self.repo.upsert_dtc_code(
            context_key=record.context_key,
            code=record.code,
            standard=record.standard,
            protocol=record.protocol,
            context_type=record.context.type,
            manufacturer_id=manufacturer_id,
            ecu_id=ecu_id,
            vehicle_variant_id=None,
            category=record.category,
            system=record.system,
            subsystem=record.subsystem,
            severity_source=record.flags.severity_label,
            version_id=self._version_ids[bundle.slug],
            created_at=self.now,
        )
        self._claim("dtc_code", code_id, "identity", record, bundle, source_record_id,
                    {"code": record.code, "standard": record.standard,
                     "context": record.context_key})

        # definitions ------------------------------------------------------
        for definition in record.definitions:
            content_hash = definition_content_hash(definition.title, definition.description)
            if not (definition.title or definition.description):
                self.stats.record_skip("empty_definition")
                continue
            key = (code_id, definition.language, content_hash)
            definition_id = self._definitions.get(key)
            if definition_id is None:
                self.conn.execute(
                    """
                    INSERT INTO dtc_definitions (dtc_code_id, language, title, description,
                        content_hash, verification_status)
                    VALUES (?,?,?,?,?,'source_reported')
                    ON CONFLICT(dtc_code_id, language, content_hash) DO NOTHING
                    """,
                    (code_id, definition.language, definition.title or None,
                     definition.description or None, content_hash),
                )
                row = self.conn.execute(
                    "SELECT id FROM dtc_definitions WHERE dtc_code_id = ? AND language = ? "
                    "AND content_hash = ?",
                    (code_id, definition.language, content_hash),
                ).fetchone()
                definition_id = int(row[0])
                self._definitions[key] = definition_id
                self.stats.definitions += 1
            self._claim("dtc_definition", definition_id, "text", record, bundle, source_record_id,
                        {"title": definition.title, "description": definition.description,
                         "language": definition.language})

        # causes -----------------------------------------------------------
        for cause in record.causes:
            self.conn.execute(
                """
                INSERT INTO dtc_causes (dtc_code_id, cause_key, likelihood)
                VALUES (?,?,?) ON CONFLICT(dtc_code_id, cause_key) DO NOTHING
                """,
                (code_id, cause.key, cause.likelihood),
            )
            cause_id = int(
                self.conn.execute(
                    "SELECT id FROM dtc_causes WHERE dtc_code_id = ? AND cause_key = ?",
                    (code_id, cause.key),
                ).fetchone()[0]
            )
            for language, label in cause.labels.items():
                self.conn.execute(
                    "INSERT INTO dtc_cause_texts (cause_id, language, label) VALUES (?,?,?) "
                    "ON CONFLICT(cause_id, language) DO NOTHING",
                    (cause_id, language, label),
                )
            self._claim("dtc_cause", cause_id, "label", record, bundle, source_record_id,
                        {"key": cause.key, "labels": cause.labels, "likelihood": cause.likelihood})
            self.stats.causes = self._count("dtc_causes")

        # symptoms ---------------------------------------------------------
        for symptom in record.symptoms:
            self.conn.execute(
                "INSERT INTO dtc_symptoms (dtc_code_id, symptom_key) VALUES (?,?) "
                "ON CONFLICT(dtc_code_id, symptom_key) DO NOTHING",
                (code_id, symptom.key),
            )
            symptom_id = int(
                self.conn.execute(
                    "SELECT id FROM dtc_symptoms WHERE dtc_code_id = ? AND symptom_key = ?",
                    (code_id, symptom.key),
                ).fetchone()[0]
            )
            for language, text in symptom.texts.items():
                self.conn.execute(
                    "INSERT INTO dtc_symptom_texts (symptom_id, language, text) VALUES (?,?,?) "
                    "ON CONFLICT(symptom_id, language) DO NOTHING",
                    (symptom_id, language, text),
                )
            self._claim("dtc_symptom", symptom_id, "text", record, bundle, source_record_id,
                        {"key": symptom.key, "texts": symptom.texts})
            self.stats.symptoms = self._count("dtc_symptoms")

        # tests ------------------------------------------------------------
        for test in record.tests:
            self.conn.execute(
                """
                INSERT INTO dtc_tests (dtc_code_id, test_key, kind, expected, requires_tool)
                VALUES (?,?,?,?,?) ON CONFLICT(dtc_code_id, test_key) DO NOTHING
                """,
                (code_id, test.key, test.kind, test.expected, test.requires_tool),
            )
            test_id = int(
                self.conn.execute(
                    "SELECT id FROM dtc_tests WHERE dtc_code_id = ? AND test_key = ?",
                    (code_id, test.key),
                ).fetchone()[0]
            )
            for language, text in test.texts.items():
                self.conn.execute(
                    "INSERT INTO dtc_test_texts (test_id, language, text) VALUES (?,?,?) "
                    "ON CONFLICT(test_id, language) DO NOTHING",
                    (test_id, language, text),
                )
            self._claim("dtc_test", test_id, "text", record, bundle, source_record_id,
                        {"key": test.key, "texts": test.texts})
            self.stats.tests = self._count("dtc_tests")

        # repairs ----------------------------------------------------------
        for repair in record.repairs:
            self.conn.execute(
                """
                INSERT INTO dtc_repairs (dtc_code_id, repair_key, difficulty, diy_possible,
                    cost_min, cost_max, currency, hours_min, hours_max)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(dtc_code_id, repair_key) DO NOTHING
                """,
                (code_id, repair.key, repair.difficulty,
                 None if repair.diy_possible is None else int(repair.diy_possible),
                 repair.cost_min, repair.cost_max, repair.currency,
                 repair.hours_min, repair.hours_max),
            )
            repair_id = int(
                self.conn.execute(
                    "SELECT id FROM dtc_repairs WHERE dtc_code_id = ? AND repair_key = ?",
                    (code_id, repair.key),
                ).fetchone()[0]
            )
            for language, text in repair.texts.items():
                self.conn.execute(
                    "INSERT INTO dtc_repair_texts (repair_id, language, text) VALUES (?,?,?) "
                    "ON CONFLICT(repair_id, language) DO NOTHING",
                    (repair_id, language, text),
                )
            self._claim("dtc_repair", repair_id, "estimate", record, bundle, source_record_id,
                        repair.model_dump(mode="json"))
            self.stats.repairs = self._count("dtc_repairs")

        # components -------------------------------------------------------
        for component in record.components:
            self.conn.execute(
                "INSERT INTO dtc_components (dtc_code_id, component_key) VALUES (?,?) "
                "ON CONFLICT(dtc_code_id, component_key) DO NOTHING",
                (code_id, component.key),
            )
            component_id = int(
                self.conn.execute(
                    "SELECT id FROM dtc_components WHERE dtc_code_id = ? AND component_key = ?",
                    (code_id, component.key),
                ).fetchone()[0]
            )
            labels = dict(component.labels)
            derived = False
            if not labels:
                # the source publishes a machine key only; give the client a
                # readable label and record that it was derived, not translated
                labels = {"en": humanize_key(component.key)}
                derived = True
            for language, label in labels.items():
                self.conn.execute(
                    "INSERT INTO dtc_component_texts (component_id, language, label) VALUES (?,?,?) "
                    "ON CONFLICT(component_id, language) DO NOTHING",
                    (component_id, language, label),
                )
            self._claim("dtc_component", component_id, "label", record, bundle, source_record_id,
                        labels, is_derived=derived,
                        notes="derived from the machine key" if derived else None)
            self.stats.components = self._count("dtc_components")

        # related codes ----------------------------------------------------
        for related in record.related_codes:
            if related == record.code:
                continue
            self.conn.execute(
                "INSERT INTO dtc_related_codes (dtc_code_id, related_code, relation_type) "
                "VALUES (?,?,'related') ON CONFLICT(dtc_code_id, related_code, relation_type) "
                "DO NOTHING",
                (code_id, related),
            )
            self._claim("dtc_code", code_id, f"related_code:{related}", record, bundle,
                        source_record_id, related)
            self.stats.related_codes = self._count("dtc_related_codes")

        # flags ------------------------------------------------------------
        flags = record.flags
        flag_values = {
            "mil": flags.mil,
            "emissions_relevant": flags.emissions_relevant,
            "drive_cycle_required": flags.drive_cycle_required,
            "limp_mode_possible": flags.limp_mode_possible,
        }
        if any(value is not None for value in flag_values.values()):
            self.conn.execute(
                """
                INSERT INTO dtc_flags (dtc_code_id, mil, emissions_relevant, drive_cycle_required,
                    limp_mode_possible)
                VALUES (?,?,?,?,?)
                ON CONFLICT(dtc_code_id) DO UPDATE SET
                    mil = COALESCE(dtc_flags.mil, excluded.mil),
                    emissions_relevant = COALESCE(dtc_flags.emissions_relevant,
                                                  excluded.emissions_relevant),
                    drive_cycle_required = COALESCE(dtc_flags.drive_cycle_required,
                                                    excluded.drive_cycle_required),
                    limp_mode_possible = COALESCE(dtc_flags.limp_mode_possible,
                                                  excluded.limp_mode_possible)
                """,
                (code_id, _bit(flags.mil), _bit(flags.emissions_relevant),
                 _bit(flags.drive_cycle_required), _bit(flags.limp_mode_possible)),
            )
            self.stats.flags = self._count("dtc_flags")
        self._claim("dtc_code", code_id, "flags", record, bundle, source_record_id, flag_values)

        # evidence ---------------------------------------------------------
        # Upstream citations are data, not metadata: without them a reviewer
        # cannot check a statement, so they get their own rows.
        stored_evidence = 0
        for url in record.evidence_urls:
            cur = self.conn.execute(
                "INSERT INTO dtc_evidence_sources (dtc_code_id, url, kind) VALUES (?,?,'source') "
                "ON CONFLICT(dtc_code_id, url) DO NOTHING",
                (code_id, url),
            )
            stored_evidence += max(int(cur.rowcount or 0), 0)
        for reference in record.references:
            cur = self.conn.execute(
                "INSERT INTO dtc_evidence_sources (dtc_code_id, url, kind, label) "
                "VALUES (?,?,'reference',?) ON CONFLICT(dtc_code_id, url) DO NOTHING",
                (code_id, reference, reference),
            )
            stored_evidence += max(int(cur.rowcount or 0), 0)
        if record.references or record.evidence_urls:
            self._claim("dtc_code", code_id, "evidence", record, bundle, source_record_id,
                        {"references": record.references, "evidence": record.evidence_urls},
                        notes=(
                            f"{len(record.evidence_urls)} source link(s), "
                            f"{len(record.references)} reference(s), "
                            f"{stored_evidence} new row(s) in dtc_evidence_sources"
                        ))

    # ------------------------------------------------------------------
    # other record types
    # ------------------------------------------------------------------
    def _load_pid(self, record: NormalizedPid, bundle: SourceBundle) -> None:
        source_record_id = self._source_record(record, bundle)
        pid_id = self.repo.upsert_pid(
            mode=record.mode,
            pid=record.pid,
            scope=record.scope,
            bytes_=record.bytes,
            unit=record.unit,
            formula=record.formula,
            range_min=record.range_min,
            range_max=record.range_max,
            signal_id=record.signal_id,
            path=record.path,
            fmt_json=json.dumps(record.fmt, sort_keys=True) if record.fmt else None,
        )
        for language, name in record.names.items():
            self.repo.add_pid_text(pid_id, language, name)
        self._claim("pid", pid_id, "definition", record, bundle, source_record_id,
                    {"names": record.names, "unit": record.unit,
                     "formula": record.formula, "range": [record.range_min, record.range_max]})
        self.stats.pids = self._count("pids")

    def _load_vehicle(self, record: NormalizedVehicle, bundle: SourceBundle) -> None:
        source_record_id = self._source_record(record, bundle)
        vehicle_id, variant_id = self.repo.upsert_vehicle(
            manufacturer=record.manufacturer,
            model=record.model,
            generation=record.generation,
            year_start=record.year_start,
            year_end=record.year_end,
            description=record.description,
            variant_name=record.variant_name or record.generation,
            engine_code=record.engine_code,
            power_kw=record.power_kw,
        )
        self.stats.vehicles = self._count("vehicles")
        self.stats.vehicle_variants = self._count("vehicle_variants")
        self.stats.manufacturers = self._count("manufacturers")
        entity_id = variant_id or vehicle_id
        entity_type = "vehicle_variant" if variant_id else "vehicle"
        self._claim(entity_type, entity_id, "identity", record, bundle, source_record_id,
                    {"manufacturer": record.manufacturer, "model": record.model,
                     "generation": record.generation})

    def _load_ecu(self, record: NormalizedEcu, bundle: SourceBundle) -> None:
        source_record_id = self._source_record(record, bundle)
        ecu_id = self.repo.upsert_ecu(
            name=record.name,
            vendor=record.vendor,
            model=record.model,
            variant=record.variant,
            ecu_type=record.ecu_type,
            protocol=record.protocol,
        )
        self.stats.ecus = self._count("ecus")

        if record.vehicle_variant:
            manufacturer, _, model = record.vehicle_variant.partition(" ")
            vehicle_id, variant_id = self.repo.upsert_vehicle(
                manufacturer=manufacturer or "Unknown",
                model=model or record.vehicle_variant,
                variant_name=record.vehicle_variant,
            )
            if variant_id:
                self.repo.link_vehicle_ecu(variant_id, ecu_id, record.header, record.ecu_type)
                self.stats.vehicle_variants = self._count("vehicle_variants")
            _ = vehicle_id

        self._claim("ecu", ecu_id, "identity", record, bundle, source_record_id,
                    {"name": record.name, "header": record.header, "type": record.ecu_type})

    # ------------------------------------------------------------------
    # post processing
    # ------------------------------------------------------------------
    def _mark_conflicts(self, conflicts: list[Conflict]) -> None:
        for conflict in conflicts:
            code_id = self._definitions_code_lookup(conflict.context_key)
            cur = self.conn.execute(
                """
                INSERT INTO conflicts (fingerprint, conflict_type, entity_type, entity_id,
                    dtc_code_id, code, context_key, attribute, summary, similarity, status,
                    created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,'needs_review',?)
                """,
                (conflict_fingerprint(conflict), conflict.conflict_type, "dtc_definition",
                 code_id or 0, code_id, conflict.code, conflict.context_key, conflict.attribute,
                 conflict.summary, conflict.similarity, self.now),
            )
            conflict_id = int(cur.lastrowid)
            self.stats.conflicts += 1
            for evidence in conflict.evidence:
                claim_id = None
                source_record_id = self._source_record_ids.get(
                    f"{evidence.source_slug}:{evidence.source_record_id}"
                )
                if source_record_id:
                    row = self.conn.execute(
                        "SELECT id FROM provenance_claims WHERE source_record_id = ? LIMIT 1",
                        (source_record_id,),
                    ).fetchone()
                    claim_id = int(row[0]) if row else None
                self.conn.execute(
                    """
                    INSERT INTO conflict_evidence (conflict_id, claim_id, source_slug, value_text)
                    VALUES (?,?,?,?)
                    """,
                    (conflict_id, claim_id, evidence.source_slug, evidence.value),
                )
                if evidence.content_hash and code_id and evidence.language:
                    self.conn.execute(
                        "UPDATE dtc_definitions SET verification_status = 'conflicting' "
                        "WHERE dtc_code_id = ? AND language = ? AND content_hash = ?",
                        (code_id, evidence.language, evidence.content_hash),
                    )

    def _propagate_code_status(self) -> None:
        """Aggregate statement status up to the code, so the client sees one value.

        A code is ``verified`` when at least one of its statements is corroborated,
        ``conflicting`` when its sources disagree, and ``unverified`` only when
        every statement is empty.
        """
        self.conn.execute(
            """
            UPDATE provenance_claims SET verification_status = COALESCE((
                SELECT CASE
                    WHEN SUM(d.verification_status = 'verified') > 0 THEN 'verified'
                    WHEN SUM(d.verification_status = 'conflicting') > 0 THEN 'conflicting'
                    WHEN SUM(d.verification_status = 'unverified') = COUNT(*) THEN 'unverified'
                    ELSE 'source_reported'
                END
                FROM dtc_definitions d WHERE d.dtc_code_id = provenance_claims.entity_id
            ), verification_status)
            WHERE entity_type = 'dtc_code'
            """
        )

    def _apply_reviews(self, reviews: ReviewStore | None) -> dict[str, int]:
        """Re-apply human decisions so a reviewed conflict is never re-opened."""
        if reviews is None or not reviews.decisions:
            return {"applied": 0, "canonical_overrides": 0, "unmatched": 0}
        stats = reviews.apply(self.conn)
        self.stats.conflicts_resolved = int(
            self.conn.execute(
                "SELECT COUNT(*) FROM conflicts WHERE status <> 'needs_review'"
            ).fetchone()[0]
        )
        return stats

    def _definitions_code_lookup(self, context_key: str) -> int | None:
        return self.repo._codes.get(context_key)

    def _set_canonical_and_verification(self) -> None:
        priorities = self._definition_priorities()
        grouped: dict[tuple[int, str], list[tuple[int, int, int, str]]] = {}
        for definition_id, code_id, language, length in self._definition_rows():
            priority = priorities.get(definition_id, 99)
            grouped.setdefault((code_id, language), []).append(
                (priority, -length, definition_id, language)
            )

        canonical_ids: list[int] = []
        for _, candidates in grouped.items():
            candidates.sort()
            canonical_ids.append(candidates[0][2])

        self.conn.execute("UPDATE dtc_definitions SET is_canonical = 0")
        self.conn.executemany(
            "UPDATE dtc_definitions SET is_canonical = 1 WHERE id = ?",
            [(definition_id,) for definition_id in canonical_ids],
        )

        # verification: >= N independent lineages corroborate the statement
        min_lineages = self.settings.rules.min_corroborating_lineages
        self.conn.execute(
            """
            UPDATE dtc_definitions SET
                verification_status = CASE
                    WHEN verification_status = 'conflicting' THEN 'conflicting'
                    WHEN lineage_count >= ? THEN 'verified'
                    ELSE 'source_reported'
                END,
                confidence = ROUND(MIN(1.0, lineage_count * 0.5), 2)
            FROM (
                SELECT d.id AS definition_id, COUNT(DISTINCT s.lineage_group) AS lineage_count
                FROM dtc_definitions d
                JOIN provenance_claims p
                  ON p.entity_type = 'dtc_definition' AND p.entity_id = d.id
                JOIN data_sources s ON s.id = p.source_id
                GROUP BY d.id
            ) AS agg
            WHERE agg.definition_id = dtc_definitions.id
            """,
            (min_lineages,),
        )

        # claims inherit their entity's aggregate status
        self.conn.execute(
            """
            UPDATE provenance_claims SET verification_status = COALESCE((
                SELECT d.verification_status FROM dtc_definitions d
                WHERE provenance_claims.entity_type = 'dtc_definition'
                  AND d.id = provenance_claims.entity_id
            ), verification_status)
            WHERE entity_type = 'dtc_definition'
            """
        )

        self._verify_by_headline(min_lineages)

        # a canonical definition must have real text
        self.conn.execute(
            """
            UPDATE dtc_definitions SET verification_status = 'unverified'
            WHERE is_canonical = 1
              AND (title IS NULL OR TRIM(title) = '')
              AND (description IS NULL OR TRIM(description) = '')
            """
        )

    def _verify_by_headline(self, min_lineages: int) -> None:
        """Corroboration is about meaning, not byte equality.

        One source stores a title plus a paragraph, another only the title. The
        statements agree, so each of them is corroborated by the other lineage -
        even though they are two rows because their text differs.
        """
        from ..identity import headline
        from ..normalizers.text import clean_text
        from ..utils.textsim import canonical_form

        rows = self.conn.execute(
            "SELECT id, dtc_code_id, language, title, description, verification_status "
            "FROM dtc_definitions"
        ).fetchall()

        lineages: dict[int, set[str]] = {}
        for definition_id, _code_id, _language, _title, _description, _status in rows:
            claims = self.conn.execute(
                """
                SELECT DISTINCT s.lineage_group
                FROM provenance_claims p JOIN data_sources s ON s.id = p.source_id
                WHERE p.entity_type = 'dtc_definition' AND p.entity_id = ?
                """,
                (int(definition_id),),
            ).fetchall()
            lineages[int(definition_id)] = {row[0] for row in claims if row[0]}

        groups: dict[tuple[int, str, str], list[int]] = {}
        for definition_id, code_id, language, title, description, _status in rows:
            class _Probe:
                pass

            probe = _Probe()
            probe.title = clean_text(title)
            probe.description = clean_text(description)
            text = canonical_form(headline(probe))
            if not text:
                continue
            groups.setdefault((int(code_id), str(language), text), []).append(int(definition_id))

        updates: list[tuple[float, int]] = []
        for members in groups.values():
            union: set[str] = set()
            for member in members:
                union |= lineages.get(member, set())
            if len(union) < min_lineages:
                continue
            confidence = round(min(1.0, len(union) * 0.5), 2)
            updates.extend((confidence, member) for member in members)

        if updates:
            self.conn.executemany(
                """
                UPDATE dtc_definitions
                SET verification_status = 'verified', confidence = ?
                WHERE id = ? AND verification_status <> 'conflicting'
                """,
                updates,
            )

    def _definition_rows(self) -> list[tuple[int, int, str, int]]:
        rows = self.conn.execute(
            "SELECT id, dtc_code_id, language, LENGTH(COALESCE(title,'') || COALESCE(description,'')) "
            "FROM dtc_definitions"
        ).fetchall()
        return [(int(r[0]), int(r[1]), str(r[2]), int(r[3] or 0)) for r in rows]

    def _definition_priorities(self) -> dict[int, int]:
        rows = self.conn.execute(
            """
            SELECT p.entity_id, s.slug
            FROM provenance_claims p JOIN data_sources s ON s.id = p.source_id
            WHERE p.entity_type = 'dtc_definition'
            """
        ).fetchall()
        priorities: dict[int, int] = {}
        for entity_id, slug in rows:
            value = SOURCE_PRECEDENCE.get(slug, 99)
            current = priorities.get(int(entity_id))
            if current is None or value < current:
                priorities[int(entity_id)] = value
        return priorities

    def _store_duplicate_groups(self, groups: list[DuplicateGroup]) -> None:
        for group in groups:
            cur = self.conn.execute(
                """
                INSERT INTO duplicate_groups (group_key, match_type, reason, member_count,
                    canonical_entity, canonical_entity_id, created_at)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(group_key, match_type) DO NOTHING
                """,
                (group.group_key, group.match_type, group.reason, len(group.members),
                 "source_record" if group.match_type != "code_context_variants" else "dtc_code",
                 self._source_record_ids.get(group.canonical) if group.canonical else None,
                 self.now),
            )
            if cur.rowcount == 0:
                continue
            group_id = int(cur.lastrowid)
            self.stats.duplicate_groups += 1
            for member in group.members:
                if group.match_type == "code_context_variants":
                    self.conn.execute(
                        """
                        INSERT INTO duplicate_members (group_id, entity_type, entity_ref, entity_id)
                        VALUES (?, 'dtc_code_context', ?, ?)
                        ON CONFLICT(group_id, entity_type, entity_ref) DO NOTHING
                        """,
                        (group_id, member, self.repo._codes.get(member)),
                    )
                else:
                    self.conn.execute(
                        """
                        INSERT INTO duplicate_members (group_id, entity_type, entity_ref, entity_id,
                            similarity, reason)
                        VALUES (?, 'source_record', ?, ?, ?, ?)
                        ON CONFLICT(group_id, entity_type, entity_ref) DO NOTHING
                        """,
                        (group_id, member, self._source_record_ids.get(member), group.similarity,
                         group.reason),
                    )

    def _compute_risk(self) -> None:
        rows = self.conn.execute(
            "SELECT dtc_code_id, mil, emissions_relevant, limp_mode_possible, "
            "drive_cycle_required FROM dtc_flags"
        ).fetchall()
        for row in rows:
            code_id = int(row["dtc_code_id"])
            score = 0
            basis: dict[str, Any] = {}
            if row["mil"]:
                score += 1
                basis["mil"] = True
            if row["emissions_relevant"]:
                score += 1
                basis["emissions_relevant"] = True
            if row["limp_mode_possible"]:
                score += 2
                basis["limp_mode_possible"] = True
            if row["drive_cycle_required"]:
                basis["drive_cycle_required"] = True
            if score == 0:
                level, note = None, "no severity flags available from any source"
            elif score == 1:
                level, note = "low", "MIL only"
            elif score <= 3:
                level, note = "medium", "MIL plus emissions or drivability impact"
            else:
                level, note = "high", "MIL + emissions relevance + possible limp mode"
            basis.update({"score": score, "rule": RISK_RULE_ID, "explanation": note})

            self.conn.execute(
                "UPDATE dtc_flags SET risk_level = ?, risk_rule_id = ?, risk_basis_json = ? "
                "WHERE dtc_code_id = ?",
                (level, RISK_RULE_ID, json.dumps(basis, sort_keys=True), code_id),
            )
            source_row = self.conn.execute(
                "SELECT source_id, data_version_id FROM provenance_claims "
                "WHERE entity_type = 'dtc_code' AND entity_id = ? LIMIT 1",
                (code_id,),
            ).fetchone()
            if source_row:
                self.repo.add_claim(
                    entity_type="dtc_flags",
                    entity_id=code_id,
                    attribute="risk_level",
                    source_id=int(source_row["source_id"]),
                    version_id=int(source_row["data_version_id"]),
                    source_record_id=None,
                    value_hash=sha256_text(f"{level}:{json.dumps(basis, sort_keys=True)}"),
                    extracted_at=self.now,
                    extraction_method=f"rule:{RISK_RULE_ID}",
                    is_derived=True,
                    notes=note,
                )
                self.stats.claims += 1

    def _count(self, table: str) -> int:
        return int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _bit(value: bool | None) -> int | None:
    return None if value is None else int(bool(value))
