"""Code, text and manufacturer normalization."""

from __future__ import annotations

import pytest

from autodoctor_data_engine.normalizers import (
    canonical_manufacturer,
    clean_text,
    code_category,
    infer_standard,
    is_valid_code,
    normalize_code,
    normalize_language,
    normalize_related_code,
    normalize_url,
    slug_key,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("p0301", "P0301"),
        ("  P0420  ", "P0420"),
        ("DTC P0171", "P0171"),
        ("P0-301", "P0301"),
        ("\u200bP0301", "P0301"),
        ("0x0F4231", "0F4231"),
        ("P0301.", "P0301"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_code(raw, expected) -> None:
    assert normalize_code(raw) == expected


def test_normalize_related_code_matches_code_rules() -> None:
    assert normalize_related_code(" p0300 ") == "P0300"


@pytest.mark.parametrize(
    "code, valid",
    [
        ("P0301", True),
        ("U0100", True),
        ("B0001", True),
        ("C0035", True),
        ("P000A", True),
        ("P15O9", False),  # letter O instead of a zero
        ("X0301", False),
        ("P03011", False),
        ("0F4231", True),  # UDS DTC
        ("", False),
    ],
)
def test_is_valid_code(code, valid) -> None:
    assert is_valid_code(code) is valid


def test_code_category() -> None:
    assert code_category("P0301") == "powertrain"
    assert code_category("B1234") == "body"
    assert code_category("U0100") == "network"
    assert code_category("") is None


def test_infer_standard_prefers_declared_value() -> None:
    assert infer_standard("P0301", declared="iso_15031_6", manufacturer_specific=True) == "iso_15031_6"


def test_infer_standard_uses_the_source_scope() -> None:
    # a publisher that files a P1xxx code in a manufacturer layer
    assert infer_standard("P1690", manufacturer_specific=True) == "manufacturer_specific"
    # a publisher that files the same code in the generic layer is taken at its word
    assert infer_standard("P1690", manufacturer_specific=False) == "sae_j2012"


def test_infer_standard_falls_back_to_the_code_shape() -> None:
    assert infer_standard("P0301") == "sae_j2012"
    assert infer_standard("P1690") == "manufacturer_specific"


def test_infer_standard_detects_uds() -> None:
    assert infer_standard("0F4231") == "uds"


def test_clean_text_collapses_whitespace_and_zero_width() -> None:
    assert clean_text("  too \t many\u200b spaces \n\n\nnext ") == "too many spaces\n\nnext"
    assert clean_text("   ") is None
    assert clean_text(None) is None


def test_normalize_language() -> None:
    assert normalize_language("EN-us") == "en"
    assert normalize_language("de_DE") == "de"
    assert normalize_language("ara") == "ar"
    assert normalize_language(None) == "en"
    assert normalize_language("xx") == "xx"


def test_normalize_url() -> None:
    assert normalize_url("https://WWW.Example.COM/path/") == "https://example.com/path"
    assert normalize_url("www.example.com") == "https://example.com"
    assert normalize_url("sae:J2012") == "sae:J2012"


@pytest.mark.parametrize(
    "label, expected",
    [
        ("CHEVY", "Chevrolet"),
        ("Mercedes", "Mercedes-Benz"),
        ("mercedes-benz", "Mercedes-Benz"),
        ("VW", "Volkswagen"),
        ("GENERIC", None),
        ("OTHER", None),
        ("saej2012.2002", None),
        (None, None),
        ("Subaru", "Subaru"),
    ],
)
def test_canonical_manufacturer(label, expected) -> None:
    assert canonical_manufacturer(label) == expected


def test_slug_key_is_stable_and_ascii() -> None:
    assert slug_key("Zündkerze verschlissen!") == "zundkerze_verschlissen"
    assert slug_key("  ") == "unnamed"
