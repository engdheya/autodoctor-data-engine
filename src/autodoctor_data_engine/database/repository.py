"""Low level persistence helpers with in-process caches.

The loader inserts tens of thousands of rows; going back to SQLite for every
identity lookup would dominate the runtime, so resolved ids are cached here.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from ..normalizers.manufacturers import manufacturer_slug


class Repository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._manufacturers: dict[str, int] = {}
        self._ecus: dict[str, int] = {}
        self._vehicles: dict[tuple[str, str, str | None], int] = {}
        self._variants: dict[tuple[int, str], int] = {}
        self._codes: dict[str, int] = {}
        self._pids: dict[tuple[str, str, str, str | None], int] = {}
        self._sources: dict[str, int] = {}
        self._versions: dict[tuple[int, str], int] = {}

    # -- sources -----------------------------------------------------------
    def upsert_source(self, source, created_at: str) -> int:
        if source.slug in self._sources:
            return self._sources[source.slug]
        lic = source.licence
        self.conn.execute(
            """
            INSERT INTO data_sources (slug, name, repo_url, code_license, data_license,
                data_license_url, contents_license, attribution_required, share_alike,
                redistribution_allowed, commercial_use_allowed, legal_review_status,
                lineage_group, homepage, notes, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(slug) DO UPDATE SET
                name = excluded.name,
                repo_url = excluded.repo_url,
                code_license = excluded.code_license,
                data_license = excluded.data_license,
                data_license_url = excluded.data_license_url,
                contents_license = excluded.contents_license,
                attribution_required = excluded.attribution_required,
                share_alike = excluded.share_alike,
                redistribution_allowed = excluded.redistribution_allowed,
                commercial_use_allowed = excluded.commercial_use_allowed,
                legal_review_status = excluded.legal_review_status,
                lineage_group = excluded.lineage_group,
                notes = excluded.notes
            """,
            (
                source.slug,
                source.name,
                source.repo_url,
                lic.code,
                lic.data,
                lic.data_url,
                lic.contents,
                int(lic.attribution_required),
                int(lic.share_alike),
                None if lic.redistribution_allowed is None else int(lic.redistribution_allowed),
                None if lic.commercial_use_allowed is None else int(lic.commercial_use_allowed),
                lic.legal_review,
                source.lineage,
                source.repo_url,
                source.notes or None,
                created_at,
            ),
        )
        source_id = int(
            self.conn.execute("SELECT id FROM data_sources WHERE slug = ?", (source.slug,)).fetchone()[0]
        )
        self._sources[source.slug] = source_id
        return source_id

    def upsert_version(
        self,
        source_id: int,
        commit_sha: str,
        retrieved_at: str,
        file_count: int,
        record_count: int,
        content_hash: str,
        version_label: str | None = None,
    ) -> int:
        key = (source_id, commit_sha)
        if key in self._versions:
            return self._versions[key]
        self.conn.execute(
            """
            INSERT INTO data_versions (source_id, version_label, commit_sha, retrieved_at,
                file_count, record_count, content_hash)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(source_id, commit_sha) DO UPDATE SET
                file_count = excluded.file_count,
                record_count = excluded.record_count,
                content_hash = excluded.content_hash,
                version_label = excluded.version_label
            """,
            (source_id, version_label, commit_sha, retrieved_at, file_count, record_count, content_hash),
        )
        version_id = int(
            self.conn.execute(
                "SELECT id FROM data_versions WHERE source_id = ? AND commit_sha = ?",
                (source_id, commit_sha),
            ).fetchone()[0]
        )
        self._versions[key] = version_id
        return version_id

    def upsert_source_file(
        self, version_id: int, path: str, sha256: str, size_bytes: int, record_type: str | None,
        record_count: int = 0,
    ) -> int:
        self.conn.execute(
            """
            INSERT INTO source_files (data_version_id, path, sha256, size_bytes, record_count, record_type)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(data_version_id, path) DO UPDATE SET
                sha256 = excluded.sha256,
                size_bytes = excluded.size_bytes,
                record_count = excluded.record_count,
                record_type = excluded.record_type
            """,
            (version_id, path, sha256, size_bytes, record_count, record_type),
        )
        return int(
            self.conn.execute(
                "SELECT id FROM source_files WHERE data_version_id = ? AND path = ?",
                (version_id, path),
            ).fetchone()[0]
        )

    def insert_source_record(
        self,
        source_file_id: int,
        source_record_id: str,
        record_type: str,
        raw_hash: str,
        raw_archive_path: str,
        ingested_at: str,
        raw_json: str | None = None,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO source_records (source_file_id, source_record_id, record_type, raw_hash,
                raw_archive_path, raw_json, ingested_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(source_file_id, source_record_id) DO UPDATE SET
                raw_hash = excluded.raw_hash,
                raw_archive_path = excluded.raw_archive_path
            """,
            (source_file_id, source_record_id, record_type, raw_hash, raw_archive_path,
             raw_json, ingested_at),
        )
        if cur.lastrowid:
            return int(cur.lastrowid)
        return int(
            self.conn.execute(
                "SELECT id FROM source_records WHERE source_file_id = ? AND source_record_id = ?",
                (source_file_id, source_record_id),
            ).fetchone()[0]
        )

    # -- entities ----------------------------------------------------------
    def upsert_manufacturer(self, name: str, country: str | None = None) -> int:
        if name in self._manufacturers:
            return self._manufacturers[name]
        self.conn.execute(
            "INSERT INTO manufacturers (slug, name, country) VALUES (?,?,?) "
            "ON CONFLICT(slug) DO UPDATE SET name = excluded.name",
            (manufacturer_slug(name), name, country),
        )
        row = self.conn.execute("SELECT id FROM manufacturers WHERE slug = ?",
                                (manufacturer_slug(name),)).fetchone()
        self._manufacturers[name] = int(row[0])
        return int(row[0])

    def upsert_ecu(self, name: str, vendor: str | None = None, model: str | None = None,
                   variant: str | None = None, ecu_type: str | None = None,
                   protocol: str | None = None, notes: str | None = None) -> int:
        if name in self._ecus:
            return self._ecus[name]
        self.conn.execute(
            """
            INSERT INTO ecus (name, vendor, model, variant, ecu_type, protocol, notes)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(name) DO UPDATE SET
                vendor = COALESCE(excluded.vendor, ecus.vendor),
                model = COALESCE(excluded.model, ecus.model),
                ecu_type = COALESCE(excluded.ecu_type, ecus.ecu_type),
                protocol = COALESCE(excluded.protocol, ecus.protocol)
            """,
            (name, vendor, model, variant, ecu_type, protocol, notes),
        )
        ecu_id = int(self.conn.execute("SELECT id FROM ecus WHERE name = ?", (name,)).fetchone()[0])
        self._ecus[name] = ecu_id
        return ecu_id

    def upsert_vehicle(
        self,
        manufacturer: str,
        model: str,
        generation: str | None = None,
        year_start: int | None = None,
        year_end: int | None = None,
        description: str | None = None,
        variant_name: str | None = None,
        engine_code: str | None = None,
        power_kw: float | None = None,
    ) -> tuple[int, int | None]:
        manufacturer_id = self.upsert_manufacturer(manufacturer)
        key = (manufacturer, model, generation)
        vehicle_id = self._vehicles.get(key)
        if vehicle_id is None:
            self.conn.execute(
                """
                INSERT INTO vehicles (manufacturer_id, model, generation, year_start, year_end, description)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(manufacturer_id, model, generation) DO UPDATE SET
                    year_start = COALESCE(vehicles.year_start, excluded.year_start),
                    year_end = COALESCE(vehicles.year_end, excluded.year_end),
                    description = COALESCE(vehicles.description, excluded.description)
                """,
                (manufacturer_id, model, generation, year_start, year_end, description),
            )
            vehicle_id = int(
                self.conn.execute(
                    "SELECT id FROM vehicles WHERE manufacturer_id = ? AND model = ? "
                    "AND IFNULL(generation, '') = IFNULL(?, '')",
                    (manufacturer_id, model, generation),
                ).fetchone()[0]
            )
            self._vehicles[key] = vehicle_id

        variant_id = None
        if variant_name:
            vkey = (vehicle_id, variant_name)
            variant_id = self._variants.get(vkey)
            if variant_id is None:
                self.conn.execute(
                    """
                    INSERT INTO vehicle_variants (vehicle_id, name, year_start, year_end,
                        engine_code, power_kw)
                    VALUES (?,?,?,?,?,?)
                    ON CONFLICT(vehicle_id, name) DO UPDATE SET
                        year_start = COALESCE(vehicle_variants.year_start, excluded.year_start),
                        year_end = COALESCE(vehicle_variants.year_end, excluded.year_end),
                        engine_code = COALESCE(vehicle_variants.engine_code, excluded.engine_code),
                        power_kw = COALESCE(vehicle_variants.power_kw, excluded.power_kw)
                    """,
                    (vehicle_id, variant_name, year_start, year_end, engine_code, power_kw),
                )
                variant_id = int(
                    self.conn.execute(
                        "SELECT id FROM vehicle_variants WHERE vehicle_id = ? AND name = ?",
                        (vehicle_id, variant_name),
                    ).fetchone()[0]
                )
                self._variants[vkey] = variant_id
        return vehicle_id, variant_id

    def link_vehicle_ecu(self, variant_id: int, ecu_id: int | None, header: str | None,
                         ecu_type: str | None) -> None:
        self.conn.execute(
            """
            INSERT INTO vehicle_ecu_links (vehicle_variant_id, ecu_id, header, ecu_type)
            VALUES (?,?,?,?)
            ON CONFLICT(vehicle_variant_id, header, ecu_type) DO UPDATE SET ecu_id = excluded.ecu_id
            """,
            (variant_id, ecu_id, header, ecu_type),
        )

    def upsert_pid(
        self,
        mode: str,
        pid: str,
        scope: str,
        bytes_: int | None,
        unit: str | None,
        formula: str | None,
        range_min: float | None,
        range_max: float | None,
        signal_id: str | None,
        path: str | None,
        fmt_json: str | None,
    ) -> int:
        key = (mode, pid, scope, signal_id)
        if key in self._pids:
            return self._pids[key]
        self.conn.execute(
            """
            INSERT INTO pids (mode, pid, scope, bytes, unit, formula, range_min, range_max,
                signal_id, path, fmt_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(mode, pid, scope, signal_id) DO UPDATE SET
                unit = COALESCE(excluded.unit, pids.unit),
                formula = COALESCE(excluded.formula, pids.formula),
                fmt_json = COALESCE(excluded.fmt_json, pids.fmt_json)
            """,
            (mode, pid, scope, bytes_, unit, formula, range_min, range_max, signal_id, path, fmt_json),
        )
        row = self.conn.execute(
            "SELECT id FROM pids WHERE mode = ? AND pid = ? AND scope = ? "
            "AND IFNULL(signal_id, '') = IFNULL(?, '')",
            (mode, pid, scope, signal_id),
        ).fetchone()
        self._pids[key] = int(row[0])
        return int(row[0])

    def add_pid_text(self, pid_id: int, language: str, name: str) -> None:
        self.conn.execute(
            "INSERT INTO pid_texts (pid_id, language, name) VALUES (?,?,?) "
            "ON CONFLICT(pid_id, language) DO UPDATE SET name = excluded.name",
            (pid_id, language, name),
        )

    # -- DTC identity ------------------------------------------------------
    def upsert_dtc_code(
        self,
        context_key: str,
        code: str,
        standard: str,
        protocol: str | None,
        context_type: str,
        manufacturer_id: int | None,
        ecu_id: int | None,
        vehicle_variant_id: int | None,
        category: str | None,
        system: str | None,
        subsystem: str | None,
        severity_source: str | None,
        version_id: int | None,
        created_at: str,
    ) -> int:
        if context_key in self._codes:
            return self._codes[context_key]
        self.conn.execute(
            """
            INSERT INTO dtc_codes (code, standard, protocol, context_type, context_key,
                manufacturer_id, ecu_id, vehicle_variant_id, category, system, subsystem,
                severity_source, first_seen_version_id, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(context_key) DO UPDATE SET
                category = COALESCE(dtc_codes.category, excluded.category),
                system = COALESCE(dtc_codes.system, excluded.system),
                subsystem = COALESCE(dtc_codes.subsystem, excluded.subsystem),
                protocol = COALESCE(dtc_codes.protocol, excluded.protocol),
                severity_source = COALESCE(dtc_codes.severity_source, excluded.severity_source)
            """,
            (code, standard, protocol, context_type, context_key, manufacturer_id, ecu_id,
             vehicle_variant_id, category, system, subsystem, severity_source, version_id, created_at),
        )
        code_id = int(
            self.conn.execute("SELECT id FROM dtc_codes WHERE context_key = ?", (context_key,)).fetchone()[0]
        )
        self._codes[context_key] = code_id
        return code_id

    # -- provenance --------------------------------------------------------
    def add_claim(
        self,
        entity_type: str,
        entity_id: int,
        attribute: str,
        source_id: int,
        version_id: int,
        source_record_id: int | None,
        value_hash: str | None,
        extracted_at: str,
        extraction_method: str = "connector",
        is_derived: bool = False,
        is_translated: bool = False,
        notes: str | None = None,
    ) -> int:
        self.conn.execute(
            """
            INSERT INTO provenance_claims (entity_type, entity_id, attribute, source_id,
                data_version_id, source_record_id, value_hash, extraction_method, is_derived,
                is_translated, verification_status, extracted_at, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,'source_reported',?,?)
            ON CONFLICT(entity_type, entity_id, attribute, source_record_id, extraction_method)
            DO NOTHING
            """,
            (entity_type, entity_id, attribute, source_id, version_id, source_record_id, value_hash,
             extraction_method, int(is_derived), int(is_translated), extracted_at, notes),
        )
        row = self.conn.execute(
            """
            SELECT id FROM provenance_claims
            WHERE entity_type = ? AND entity_id = ? AND attribute = ?
              AND IFNULL(source_record_id, -1) = IFNULL(?, -1) AND extraction_method = ?
            """,
            (entity_type, entity_id, attribute, source_record_id, extraction_method),
        ).fetchone()
        return int(row[0]) if row else 0

    def claim_sources(self, entity_type: str, entity_id: int, attribute: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT p.id, p.attribute, p.verification_status, p.is_derived, p.is_translated,
                   s.slug AS source_slug, s.lineage_group, s.data_license, v.commit_sha
            FROM provenance_claims p
            JOIN data_sources s ON s.id = p.source_id
            JOIN data_versions v ON v.id = p.data_version_id
            WHERE p.entity_type = ? AND p.entity_id = ?
        """
        params: list[Any] = [entity_type, entity_id]
        if attribute:
            query += " AND p.attribute = ?"
            params.append(attribute)
        return [dict(row) for row in self.conn.execute(query, params)]
