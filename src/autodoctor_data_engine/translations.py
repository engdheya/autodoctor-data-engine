"""Human translations (currently Arabic).

None of the four upstream sources provides Arabic. The engine therefore never
generates translations: it only accepts files that name a translator, and by
default only accepts entries a reviewer has signed off.

File format (``data/translations/<language>/*.yaml``)::

    - code: P0301
      context: {type: generic}          # optional, defaults to generic
      title: "..."
      description: "..."
      translator: "..."
      reviewer: "..."                    # required when reviewed: true
      reviewed: true
      source_url: "https://..."          # optional reference used by the translator
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .normalizers.codes import normalize_code
from .normalizers.text import clean_text, normalize_language
from .parsers.yaml_loader import load_yaml


@dataclass
class TranslationEntry:
    code: str
    language: str
    title: str | None
    description: str | None
    translator: str | None
    reviewer: str | None
    reviewed: bool
    context_type: str = "generic"
    context_target: str | None = None
    source_url: str | None = None
    file_path: str = ""

    @property
    def context_key(self) -> str:
        target = "generic" if self.context_type == "generic" else (self.context_target or "").lower()
        return f"{self.code}|{self.standard}|{self.context_type}:{target}"

    @property
    def standard(self) -> str:
        if self.context_type == "generic":
            return "sae_j2012"
        return "manufacturer_specific"


class TranslationError(RuntimeError):
    pass


def translation_dir(settings: Settings) -> Path:
    return settings.root / "data" / "translations"


def load_translations(
    settings: Settings, *, include_unreviewed: bool = False
) -> tuple[list[TranslationEntry], list[str]]:
    entries: list[TranslationEntry] = []
    warnings: list[str] = []
    root = translation_dir(settings)
    if not root.is_dir():
        return entries, warnings
    for path in sorted(root.glob("*/*.yaml")):
        try:
            data = load_yaml(path) or []
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{path}: {exc}")
            continue
        if not isinstance(data, list):
            warnings.append(f"{path}: expected a list of translation entries")
            continue
        language = normalize_language(path.parent.name, "ar")
        for index, raw in enumerate(data):
            if not isinstance(raw, dict):
                warnings.append(f"{path}#{index}: not a mapping")
                continue
            code = normalize_code(raw.get("code"))
            reviewed = bool(raw.get("reviewed"))
            if not code:
                warnings.append(f"{path}#{index}: missing code")
                continue
            if reviewed and not raw.get("reviewer"):
                warnings.append(f"{path}#{index}: reviewed entry without reviewer, skipped")
                continue
            if not reviewed and not include_unreviewed:
                warnings.append(
                    f"{path}#{index}: {code} translation is not reviewed yet, skipped"
                )
                continue
            context = raw.get("context") or {}
            context_type = str(context.get("type") or "generic") if isinstance(context, dict) else "generic"
            context_target = None
            if isinstance(context, dict):
                context_target = clean_text(
                    context.get("manufacturer") or context.get("ecu") or context.get("vehicle_variant")
                )
            entries.append(
                TranslationEntry(
                    code=code,
                    language=language,
                    title=clean_text(raw.get("title")),
                    description=clean_text(raw.get("description")),
                    translator=clean_text(raw.get("translator")),
                    reviewer=clean_text(raw.get("reviewer")),
                    reviewed=reviewed,
                    context_type=context_type,
                    context_target=context_target,
                    source_url=clean_text(raw.get("source_url")),
                    file_path=str(path.relative_to(settings.root)),
                )
            )
    return entries, warnings


def export_template(conn, path: Path, *, language: str = "ar", limit: int | None = None) -> int:
    """Write a CSV of generic codes that still have no canonical translation."""
    query = """
        SELECT c.code, d.title, d.description
        FROM dtc_codes c
        JOIN dtc_definitions d ON d.dtc_code_id = c.id AND d.language = 'en' AND d.is_canonical = 1
        WHERE c.context_type = 'generic'
          AND NOT EXISTS (
              SELECT 1 FROM dtc_definitions t
              WHERE t.dtc_code_id = c.id AND t.language = ?
          )
        ORDER BY c.code
    """
    rows = conn.execute(query, (language,)).fetchall()
    if limit:
        rows = rows[:limit]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["code", "title_en", "description_en", "title_ar", "description_ar",
                         "translator", "reviewer", "reviewed"])
        for row in rows:
            writer.writerow([row["code"], row["title"] or "", row["description"] or "", "", "", "", "", "false"])
    return len(rows)
