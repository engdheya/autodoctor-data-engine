"""The delivered review package must not contradict its own data.

The README of ``deliveries/review-003`` drifted once already: it kept the old quote total
while the report next to it carried the new one. This test reads the package artifacts and
compares the numbers the documents claim with the numbers the files contain.
"""

from __future__ import annotations

import functools
import gzip
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "deliveries" / "review-003"
README = PACKAGE / "README.md"
BEFORE_AFTER = PACKAGE / "BEFORE_AFTER.md"

pytestmark = pytest.mark.skipif(
    not README.is_file(), reason="review-003 package is not present in this checkout"
)


@functools.lru_cache(maxsize=1)
def _export_summary() -> dict:
    with gzip.open(PACKAGE / "procedures" / "procedures-quoted.yaml.gz", "rt", encoding="utf-8") as handle:
        return yaml.safe_load(handle)["summary"]


@functools.lru_cache(maxsize=1)
def _pack() -> dict:
    payload = yaml.safe_load((PACKAGE / "packs" / "tier1-100-safety.yaml").read_text(encoding="utf-8"))
    return payload


def test_readme_totals_match_the_export() -> None:
    summary = _export_summary()
    text = README.read_text(encoding="utf-8")

    assert f"| **المجموع** | **{summary['quotes_total']:,}** |" in text

    labels = {
        "diagnostic_check": "فحص تشخيصي فعلي",
        "monitoring_description": "وصف مراقبة النظام",
        "technical_explanation": "شرح تقني",
        "non_procedure": "ليس إجراءً",
    }
    for category, count in summary["quotes_by_category"].items():
        assert f"| `{category}` — {labels[category]} | **{count:,}** |" in text, category

    assert f"**{summary['codes_with_diagnostic_check']}**" in text


def test_readme_pack_numbers_match_the_pack() -> None:
    pack = _pack()
    summary = pack["summary"]
    quotes = sum(len(entry["procedure"]["quoted_checks"]) for entry in pack["entries"])
    text = README.read_text(encoding="utf-8")

    assert f"**{summary['entries_with_quoted_checks']} كود / {quotes} اقتباس**" in text
    assert f"| مسوّدات عربية | **{summary['arabic_drafts']}** |" in text
    # no non-diagnostic sentence may sit inside quoted_checks of the delivered pack
    for entry in pack["entries"]:
        for quote in entry["procedure"]["quoted_checks"]:
            assert quote["category"] == "diagnostic_check", entry["code"]


def test_readme_does_not_repeat_a_file_row() -> None:
    text = README.read_text(encoding="utf-8")
    assert text.count("| `TEST_RESULTS.md` |") == 1, "TEST_RESULTS.md is listed twice"
    assert text.count("| `BEFORE_AFTER.md` |") == 1


def test_every_file_named_in_the_table_exists() -> None:
    rows = re.findall(r"^\| `([^`]+)` \|", README.read_text(encoding="utf-8"), re.MULTILINE)
    candidates = [
        name
        for name in rows
        if " " not in name and ("/" in name or name.endswith((".md", ".yaml", ".gz", ".csv", ".py")))
    ]
    assert candidates, "the file table must be parseable"
    missing = [name for name in candidates if not list(PACKAGE.glob(name))]
    assert not missing, f"documented but absent: {missing}"


def test_before_after_matches_the_current_export() -> None:
    summary = _export_summary()
    text = BEFORE_AFTER.read_text(encoding="utf-8")
    assert f"**{summary['quotes_total']:,}**" in text
    assert f"**{summary['codes_with_diagnostic_check']}**" in text
    assert f"**{summary['quotes_by_category']['diagnostic_check']}**" in text
    assert f"**{summary['codes_with_quotes']:,}**" in text


def test_notes_copy_matches_the_package_readme() -> None:
    notes = ROOT / "docs" / "REVIEW_003_NOTES.md"
    if not notes.is_file():
        pytest.skip("no notes copy in this checkout")
    assert notes.read_text(encoding="utf-8") == README.read_text(encoding="utf-8")
