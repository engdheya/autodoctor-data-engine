"""Identity helpers shared by the conflict detector and the database loader.

If the two layers computed identities differently, a conflict could point at a
definition row that does not exist. Both therefore use exactly these functions.
"""

from __future__ import annotations

from .normalizers.text import clean_text
from .utils.hashing import sha256_text


def statement_text(title: str | None, description: str | None) -> str:
    parts = [p.strip() for p in (clean_text(title), clean_text(description)) if p]
    return " — ".join(parts)


def definition_content_hash(title: str | None, description: str | None) -> str:
    return sha256_text(statement_text(title, description).casefold())


def headline(definition) -> str:
    """The comparable one-line meaning of a definition.

    Sources differ in how much prose they attach: one stores a title plus a long
    paragraph, another only a bare title. Comparing concatenated text would report
    a difference where the sources actually agree, so comparisons use the headline
    (title, falling back to the description).
    """
    return (definition.title or definition.description or "").strip()


def statement_similarity(def_a, def_b) -> float:
    """Similarity of two definitions, using the best comparable field."""
    from .utils.textsim import similarity

    score = similarity(headline(def_a), headline(def_b))
    if def_a.description and def_b.description:
        score = max(score, similarity(def_a.description, def_b.description))
    return round(score, 4)
