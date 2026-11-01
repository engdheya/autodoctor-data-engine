"""Provenance queries: answer "where did this information come from?".

For any DTC the tracker can report, per statement:

  * the source slug, repository, commit SHA and licence
  * when it was imported and from which file/record
  * whether the statement is corroborated, conflicting or unverified
  * which other sources support or contradict it
"""

from __future__ import annotations

import sqlite3
from typing import Any


class ProvenanceTracker:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ------------------------------------------------------------------
    def explain_code(
        self, code: str, *, context_key: str | None = None, language: str | None = None
    ) -> dict[str, Any]:
        code = code.strip().upper()
        query = """
            SELECT c.*, m.name AS manufacturer_name, e.name AS ecu_name
            FROM dtc_codes c
            LEFT JOIN manufacturers m ON m.id = c.manufacturer_id
            LEFT JOIN ecus e ON e.id = c.ecu_id
            WHERE c.code = ?
        """
        params: list[Any] = [code]
        if context_key:
            query += " AND c.context_key = ?"
            params.append(context_key)
        identities = [dict(row) for row in self.conn.execute(query, params)]
        if not identities:
            return {"code": code, "found": False, "contexts": []}

        contexts = []
        for identity in identities:
            code_id = identity["id"]
            definitions = self._definitions(code_id, language)
            contexts.append(
                {
                    "context_key": identity["context_key"],
                    "context_type": identity["context_type"],
                    "standard": identity["standard"],
                    "protocol": identity["protocol"],
                    "manufacturer": identity["manufacturer_name"],
                    "ecu": identity["ecu_name"],
                    "category": identity["category"],
                    "definitions": definitions,
                    "flags": self._flags(code_id),
                    "counts": self._content_counts(code_id),
                    "conflicts": self._conflicts(code_id),
                    "duplicates": self._duplicates(identity["context_key"]),
                    "evidence": self._evidence(code_id),
                }
            )
        return {"code": code, "found": True, "contexts": contexts}

    def _evidence(self, code_id: int) -> list[dict[str, Any]]:
        """Upstream citations (TSBs, standards, regulation texts)."""
        try:
            rows = self.conn.execute(
                "SELECT url, kind, label FROM dtc_evidence_sources "
                "WHERE dtc_code_id = ? ORDER BY kind, url",
                (code_id,),
            ).fetchall()
        except sqlite3.OperationalError:  # app bundles from older schema versions
            return []
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    def _definitions(self, code_id: int, language: str | None) -> list[dict[str, Any]]:
        query = "SELECT * FROM dtc_definitions WHERE dtc_code_id = ?"
        params: list[Any] = [code_id]
        if language:
            query += " AND language = ?"
            params.append(language)
        query += " ORDER BY language, is_canonical DESC, id"
        out = []
        for row in self.conn.execute(query, params):
            definition = dict(row)
            definition["claims"] = self._claims("dtc_definition", int(row["id"]))
            out.append(definition)
        return out

    def _claims(self, entity_type: str, entity_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT p.attribute, p.verification_status, p.is_derived, p.is_translated,
                   p.extracted_at, p.extraction_method,
                   s.slug AS source, s.name AS source_name, s.repo_url,
                   s.code_license, s.data_license, s.legal_review_status, s.lineage_group,
                   v.commit_sha, v.retrieved_at, v.version_label,
                   f.path AS file_path, r.source_record_id, r.raw_hash
            FROM provenance_claims p
            JOIN data_sources s ON s.id = p.source_id
            JOIN data_versions v ON v.id = p.data_version_id
            LEFT JOIN source_records r ON r.id = p.source_record_id
            LEFT JOIN source_files f ON f.id = r.source_file_id
            WHERE p.entity_type = ? AND p.entity_id = ?
            ORDER BY s.slug
            """,
            (entity_type, entity_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def _flags(self, code_id: int) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM dtc_flags WHERE dtc_code_id = ?", (code_id,)).fetchone()
        if not row:
            return None
        flags = dict(row)
        flags["claims"] = self._claims("dtc_flags", code_id)
        return flags

    def _content_counts(self, code_id: int) -> dict[str, int]:
        return {
            table: int(
                self.conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE dtc_code_id = ?", (code_id,)
                ).fetchone()[0]
            )
            for table in (
                "dtc_causes",
                "dtc_symptoms",
                "dtc_tests",
                "dtc_repairs",
                "dtc_components",
                "dtc_related_codes",
            )
        }

    def _conflicts(self, code_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT c.id, c.conflict_type, c.attribute, c.summary, c.similarity, c.status,
                   e.source_slug, e.value_text
            FROM conflicts c
            LEFT JOIN conflict_evidence e ON e.conflict_id = c.id
            WHERE c.dtc_code_id = ?
            ORDER BY c.id
            """,
            (code_id,),
        ).fetchall()
        grouped: dict[int, dict[str, Any]] = {}
        for row in rows:
            entry = grouped.setdefault(
                int(row["id"]),
                {
                    "id": int(row["id"]),
                    "type": row["conflict_type"],
                    "attribute": row["attribute"],
                    "summary": row["summary"],
                    "similarity": row["similarity"],
                    "status": row["status"],
                    "evidence": [],
                },
            )
            if row["source_slug"]:
                entry["evidence"].append(
                    {"source": row["source_slug"], "value": row["value_text"]}
                )
        return list(grouped.values())

    def _duplicates(self, context_key: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT g.id, g.match_type, g.reason
            FROM duplicate_groups g
            JOIN duplicate_members m ON m.group_id = g.id
            WHERE m.entity_ref = ? AND m.entity_type = 'dtc_code_context'
            """,
            (context_key,),
        ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    def source_summary(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT s.slug, s.name, s.repo_url, s.code_license, s.data_license,
                   s.share_alike, s.legal_review_status, s.lineage_group,
                   v.commit_sha, v.retrieved_at,
                   (SELECT COUNT(*) FROM provenance_claims p
                     WHERE p.source_id = s.id) AS claims,
                   (SELECT COUNT(DISTINCT p.entity_id) FROM provenance_claims p
                     WHERE p.source_id = s.id AND p.entity_type = 'dtc_code') AS dtc_codes
            FROM data_sources s
            LEFT JOIN data_versions v ON v.source_id = s.id
            ORDER BY s.slug
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def verification_breakdown(self) -> dict[str, dict[str, int]]:
        definitions: dict[str, int] = {}
        for row in self.conn.execute(
            "SELECT verification_status, COUNT(*) FROM dtc_definitions GROUP BY 1"
        ):
            definitions[row[0]] = int(row[1])
        claims: dict[str, int] = {}
        for row in self.conn.execute(
            "SELECT verification_status, COUNT(*) FROM provenance_claims GROUP BY 1"
        ):
            claims[row[0]] = int(row[1])
        return {"definitions": definitions, "claims": claims}
