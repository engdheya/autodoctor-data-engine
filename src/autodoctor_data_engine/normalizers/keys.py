"""Stable key derivation for reusable entities (causes, symptoms, components...)."""

from __future__ import annotations

import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slug_key(value: str, *, max_length: int = 80) -> str:
    """Turn free text into a stable snake_case key.

    Keys must be stable across imports so that the same conceptual cause coming
    from two sources can be compared and de-duplicated.
    """
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    text = text.casefold()
    text = _NON_ALNUM.sub("_", text).strip("_")
    if len(text) > max_length:
        text = text[:max_length].rstrip("_")
    return text or "unnamed"
