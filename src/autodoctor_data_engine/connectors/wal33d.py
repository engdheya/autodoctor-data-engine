"""Connector for Wal33D/dtc-database.

Layout (observed at commit 04c43d7):
    data/dtc_codes.db                      compiled SQLite, table dtc_definitions
                                           (code, manufacturer, description, type,
                                            locale, is_generic, source_file)
    data/source-data/*_codes.txt            the raw "CODE - description" lists
    android/.../assets/dtc_codes.db        a copy shipped with the Android library
    LICENSE                                MIT

The repository contains *no* causes, symptoms or repair data, and only English
text. Its value is coverage: 18,805 rows, 12,128 unique codes and 33 manufacturer
contexts - including the same code meaning different things for different makes.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from ..models import Context, Definition, NormalizedDtc, NormalizedRecord, Provenance
from ..normalizers.codes import code_category, infer_standard, normalize_code
from ..normalizers.manufacturers import canonical_manufacturer
from ..normalizers.text import clean_text, normalize_language
from ..parsers.delimited import parse_code_list
from ..parsers.sqlite_reader import connect_readonly, table_columns
from ..utils.gitinfo import commit_sha, describe, is_dirty
from .base import ConnectorError, RawRecord, SourceConnector, SourceInspection

TABLE = "dtc_definitions"
QUERY = f"SELECT code, manufacturer, description, type, locale, is_generic, source_file FROM {TABLE}"


class Wal33DConnector(SourceConnector):
    slug = "wal33d"
    record_types = ("dtc",)

    @property
    def db_path(self) -> Path:
        return self.root / "data" / "dtc_codes.db"

    # -- inspection --------------------------------------------------------
    def inspect(self) -> SourceInspection:
        root = self.require_root()
        if not self.db_path.is_file():
            raise ConnectorError(f"{self.slug}: {self.db_path} not found")
        conn = connect_readonly(self.db_path)
        try:
            columns = table_columns(conn, TABLE)
            total = conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
            unique = conn.execute(f"SELECT COUNT(DISTINCT code) FROM {TABLE}").fetchone()[0]
            generic = conn.execute(f"SELECT COUNT(*) FROM {TABLE} WHERE is_generic = 1").fetchone()[0]
            manufacturers = [
                row[0] for row in conn.execute(f"SELECT DISTINCT manufacturer FROM {TABLE} ORDER BY 1")
            ]
            locales = [row[0] for row in conn.execute(f"SELECT DISTINCT locale FROM {TABLE} ORDER BY 1")]
        finally:
            conn.close()

        text_files = sorted((root / "data" / "source-data").glob("*_codes.txt"))
        text_lines = 0
        for path in text_files:
            text_lines += sum(1 for _ in parse_code_list(path))

        warnings: list[str] = []
        if text_lines and text_lines != total:
            warnings.append(
                f"text lists hold {text_lines} parseable lines but the compiled SQLite has {total} rows"
            )
        if locales and locales != ["en"]:
            warnings.append(f"unexpected locales: {locales}")

        layout = {
            "format": "sqlite (dtc_definitions) + raw CODE - description text lists",
            "columns": columns,
            "rows": total,
            "unique_codes": unique,
            "generic_rows": generic,
            "manufacturer_specific_rows": total - generic,
            "manufacturers": manufacturers,
            "locales": locales,
            "text_files": len(text_files),
            "text_lines": text_lines,
            "record_types": ["dtc"],
            "content": ["code", "description", "manufacturer", "category"],
            "missing_content": ["causes", "symptoms", "tests", "repairs", "related_codes"],
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
            file_count=len(text_files) + 1,
            total_bytes=self.db_path.stat().st_size + sum(p.stat().st_size for p in text_files),
            layout=layout,
            licence=self.licence_dict(),
            notes=self.source.notes,
            warnings=warnings,
        )

    # -- extraction --------------------------------------------------------
    def extract(self) -> Iterator[RawRecord]:
        conn = connect_readonly(self.db_path)
        try:
            for row in conn.execute(QUERY):
                row = dict(row)
                code = normalize_code(row.get("code"))
                manufacturer = (row.get("manufacturer") or "").strip().upper()
                if not code:
                    continue
                yield RawRecord(
                    record_type="dtc",
                    source_record_id=f"{code}|{manufacturer}|{row.get('locale') or 'en'}",
                    file_path="data/dtc_codes.db",
                    payload=row,
                    extra={
                        "table": TABLE,
                        "source_file": row.get("source_file"),
                        "row_hash_columns": ["code", "manufacturer", "description", "locale"],
                    },
                )
        finally:
            conn.close()

    # -- normalization -----------------------------------------------------
    def normalize(self, raw: RawRecord, provenance_base: dict[str, Any]) -> Iterable[NormalizedRecord]:
        payload = raw.payload
        code = normalize_code(payload.get("code"))
        if not code:
            return []
        manufacturer_raw = clean_text(payload.get("manufacturer"))
        is_generic = bool(payload.get("is_generic")) or (manufacturer_raw or "").upper() == "GENERIC"
        manufacturer = canonical_manufacturer(manufacturer_raw)

        if is_generic:
            context = Context(type="generic")
        elif manufacturer:
            context = Context(type="manufacturer", manufacturer=manufacturer)
        else:
            # a non-generic label we cannot map to a real manufacturer ("OTHER")
            # must not be silently promoted to a generic statement
            context = Context(type="manufacturer", manufacturer="Unspecified")

        description = clean_text(payload.get("description"))
        definitions = (
            [Definition(language=normalize_language(payload.get("locale"), "en"), title=description)]
            if description
            else []
        )

        prov = Provenance(**provenance_base)
        if payload.get("source_file"):
            prov.notes = f"wal33d source_file={payload['source_file']}"

        category = code_category(code) or clean_text(payload.get("type"))
        return [
            NormalizedDtc(
                code=code,
                standard=infer_standard(code, manufacturer_specific=not is_generic),
                protocol="obd2" if is_generic else "manufacturer",
                category=category.lower() if category else None,
                context=context,
                definitions=definitions,
                provenance=prov,
            )
        ]
