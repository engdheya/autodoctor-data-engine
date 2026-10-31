"""Normalization layer: pure functions, no I/O, fully unit-testable."""

from .codes import (
    code_category,
    infer_standard,
    is_valid_code,
    normalize_code,
    normalize_related_code,
)
from .keys import slug_key
from .manufacturers import canonical_manufacturer, manufacturer_slug
from .text import clean_text, normalize_language, normalize_url

__all__ = [
    "normalize_code",
    "normalize_related_code",
    "is_valid_code",
    "code_category",
    "infer_standard",
    "clean_text",
    "normalize_language",
    "normalize_url",
    "canonical_manufacturer",
    "manufacturer_slug",
    "slug_key",
]
