"""Text similarity used to distinguish "same statement" from "real disagreement".

We deliberately use a cheap, explainable metric: character-level similarity of the
normalized strings, combined with a token-set Jaccard score. Both are stored with
the duplicate/conflict decision so a reviewer can see why the engine decided.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

_NON_WORD = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")


def canonical_form(text: str) -> str:
    text = (text or "").casefold().strip()
    text = _NON_WORD.sub(" ", text)
    return _WS.sub(" ", text).strip()


def token_set(text: str) -> frozenset[str]:
    return frozenset(t for t in canonical_form(text).split() if len(t) > 1)


def similarity(a: str, b: str) -> float:
    """Return a 0..1 similarity score for two free-text statements."""
    ca, cb = canonical_form(a), canonical_form(b)
    if not ca or not cb:
        return 0.0
    if ca == cb:
        return 1.0
    seq = SequenceMatcher(None, ca, cb).ratio()
    ta, tb = token_set(a), token_set(b)
    jac = len(ta & tb) / len(ta | tb) if ta and tb else 0.0
    return round(max(seq, jac), 4)
