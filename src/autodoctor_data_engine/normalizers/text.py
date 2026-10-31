"""Text, language and URL normalization."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit

_WS = re.compile(r"[ \t\u00a0]+")
_MULTINEWLINE = re.compile(r"\n{3,}")

# languages we standardise to a two letter code
_LANGUAGE_ALIASES = {
    "en": "en", "eng": "en", "english": "en", "en-us": "en", "en-gb": "en", "en_us": "en",
    "de": "de", "deu": "de", "ger": "de", "german": "de", "de-de": "de", "de_at": "de",
    "ar": "ar", "ara": "ar", "arabic": "ar", "ar-sa": "ar", "ar_ye": "ar",
    "fr": "fr", "es": "es", "it": "it", "nl": "nl", "pl": "pl", "tr": "tr", "ru": "ru",
}


def clean_text(value: object) -> str | None:
    """Normalize whitespace and unicode form; return None for empty strings."""
    if value is None:
        return None
    text = str(value)
    text = text.replace("\u200b", "").replace("\u200c", "").replace("\ufeff", "")
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WS.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _MULTINEWLINE.sub("\n\n", text).strip()
    return text or None


def normalize_language(value: str | None, default: str = "en") -> str:
    if not value:
        return default
    key = str(value).strip().lower().replace("_", "-")
    if key in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[key]
    return key.split("-")[0][:2] or default


def normalize_url(value: str) -> str | None:
    value = clean_text(value)
    if not value:
        return None
    if "://" not in value:
        if value.startswith("www."):
            value = "https://" + value
        else:
            return value
    parts = urlsplit(value)
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parts.path.rstrip("/") or ""
    return urlunsplit((parts.scheme.lower(), netloc, path, parts.query, ""))
