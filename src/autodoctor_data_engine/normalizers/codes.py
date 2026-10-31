"""DTC code normalization and classification.

Rules
  * uppercase
  * strip surrounding whitespace, zero-width characters, dashes and dots
  * a code is *not* rewritten beyond case/whitespace: P0301 stays P0301, and a
    UDS code such as 0x0F4231 stays a UDS code (it must not be coerced into the
    five-character OBD-II shape).
  * the letter defines the category; the second character defines the sub-system
    (0 = generic powertrain/body/chassis/network, 1 = manufacturer specific,
    2/3 reserved for the standard / manufacturer extensions).
"""

from __future__ import annotations

import re

from ..config import Rules

DEFAULT_RULES = Rules(
    code_pattern=r"^[PBCU][0-3][0-9A-F]{3}$",
    uds_code_pattern=r"^[0-9A-F]{6,8}$",
    similarity_threshold=0.85,
    min_corroborating_lineages=2,
    blocked_redistribution_review=(),
)

_CATEGORY_BY_LETTER = {
    "P": "powertrain",
    "B": "body",
    "C": "chassis",
    "U": "network",
}

# characters that scanners and copy/paste often inject around codes
_STRIP_CHARS = " \t\r\n\u200b\u200c\u200d\ufeff\"'`.,;:()[]{}<>-_/\\|"
_PREFIX = re.compile(r"^(?:DTC|CODE|SAE)[\s:#-]+", re.IGNORECASE)
_HEX_PREFIX = re.compile(r"^0X", re.IGNORECASE)


def normalize_code(raw: str) -> str:
    """Return the canonical form of a DTC identifier (never raises)."""
    if raw is None:
        return ""
    code = str(raw)
    code = code.replace("\u00a0", " ")
    code = _PREFIX.sub("", code.strip())
    code = code.strip(_STRIP_CHARS)
    # interior separators appear in scan-tool exports ("P0-301", "P0 301")
    code = re.sub(r"[\s\-_]+", "", code)
    upper = code.upper()
    if _HEX_PREFIX.match(upper):
        return _HEX_PREFIX.sub("", upper)
    return upper


def normalize_related_code(raw: str) -> str:
    return normalize_code(raw)


def _pattern_for(code: str) -> re.Pattern[str]:
    if re.fullmatch(DEFAULT_RULES.uds_code_pattern, code) and not re.fullmatch(
        DEFAULT_RULES.code_pattern, code
    ):
        return re.compile(DEFAULT_RULES.uds_code_pattern)
    return re.compile(DEFAULT_RULES.code_pattern)


def is_valid_code(code: str, rules: Rules | None = None) -> bool:
    """Validate a normalized code against the OBD-II or UDS patterns."""
    if not code:
        return False
    rules = rules or DEFAULT_RULES
    if re.fullmatch(rules.code_pattern, code):
        return True
    return bool(re.fullmatch(rules.uds_code_pattern, code))


def code_category(code: str) -> str | None:
    if not code:
        return None
    return _CATEGORY_BY_LETTER.get(code[0].upper())


def infer_standard(code: str, *, manufacturer_specific: bool | None = None,
                   declared: str | None = None) -> str:
    """Infer the standard a code belongs to.

    Precedence: a standard declared by the source, then the source's own
    generic/manufacturer scope, then the code shape. The second character of an
    OBD-II code implies "manufacturer specific" (1) or "generic" (0), but a source
    that explicitly files a P1xxx code under the generic layer is recorded as it
    reported it; the contradiction is surfaced as a validation warning instead of
    being silently rewritten.
    """
    if declared:
        return declared
    if not code:
        return "unknown"
    if re.fullmatch(DEFAULT_RULES.uds_code_pattern, code) and not re.fullmatch(
        DEFAULT_RULES.code_pattern, code
    ):
        return "uds"
    if manufacturer_specific is True:
        return "manufacturer_specific"
    if manufacturer_specific is False:
        return "sae_j2012"
    if len(code) >= 2 and code[0].upper() in _CATEGORY_BY_LETTER:
        if code[1] == "1":
            return "manufacturer_specific"
        if code[1] in "023":
            return "sae_j2012"
    return "unknown"


def is_prefix_manufacturer_specific(code: str) -> bool:
    """True when the standard's second character marks the code as vendor specific."""
    return bool(code) and len(code) >= 2 and code[1] == "1" and code[0].upper() in _CATEGORY_BY_LETTER
