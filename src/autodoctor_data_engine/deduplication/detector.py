"""Duplicate detection.

Three distinct phenomena are reported separately, because "same code" and
"same statement" are not the same thing:

``exact_statement``
    identical text (after normalization) for the same code, context and language.
    Safe to collapse into a single row with several provenance claims.

``near_statement``
    very similar but not identical text in the same context and language. Reported
    for review; the engine keeps both rows and marks the shorter one non-canonical.
    It never silently merges them.

``code_context_variants``
    the same code appearing in different contexts (generic vs manufacturer vs ECU).
    This is *not* duplication: P1690 means different things at Ford and at BMW, so
    the rows must stay apart. Reported for visibility only.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations

from ..config import Rules
from ..identity import headline, statement_similarity, statement_text
from ..models import NormalizedDtc
from ..utils.hashing import sha256_json
from ..utils.textsim import canonical_form


@dataclass
class StatementRef:
    record_id: str          # stable identifier of the normalized record
    code: str
    context_key: str
    language: str
    text: str
    source_slug: str
    title: str | None = None
    description: str | None = None
    definition: object | None = None


@dataclass
class DuplicateGroup:
    group_key: str
    match_type: str
    reason: str
    members: list[str] = field(default_factory=list)
    similarity: float | None = None
    canonical: str | None = None

    def to_dict(self) -> dict:
        return {
            "group_key": self.group_key,
            "match_type": self.match_type,
            "reason": self.reason,
            "member_count": len(self.members),
            "members": self.members,
            "similarity": self.similarity,
            "canonical": self.canonical,
        }


def record_id(record: NormalizedDtc) -> str:
    return f"{record.provenance.source_slug}:{record.provenance.source_record_id}"


def collect_statements(records: list[NormalizedDtc]) -> list[StatementRef]:
    out: list[StatementRef] = []
    for record in records:
        for definition in record.definitions:
            text = statement_text(definition.title, definition.description)
            if not text:
                continue
            out.append(
                StatementRef(
                    record_id=record_id(record),
                    code=record.code,
                    context_key=record.context_key,
                    language=definition.language,
                    text=headline(definition),
                    source_slug=record.provenance.source_slug,
                    title=definition.title,
                    description=definition.description,
                    definition=definition,
                )
            )
    return out


def _group_key(*parts: str) -> str:
    return sha256_json(list(parts))[:20]


def detect_duplicates(
    records: list[NormalizedDtc], rules: Rules, *, include_context_variants: bool = True
) -> tuple[list[DuplicateGroup], dict[str, int]]:
    statements = collect_statements(records)
    stats = {"statements": len(statements), "exact": 0, "near": 0, "context_variants": 0}
    groups: list[DuplicateGroup] = []

    buckets: dict[tuple[str, str, str], list[StatementRef]] = defaultdict(list)
    for statement in statements:
        buckets[(statement.code, statement.context_key, statement.language)].append(statement)

    for (code, context_key, language), members in sorted(buckets.items()):
        by_text: dict[str, list[StatementRef]] = defaultdict(list)
        for member in members:
            # punctuation and case are noise: "Threshold (Bank 1)" and
            # "Threshold Bank 1" are the same statement
            key = canonical_form(member.text)
            by_text[key].append(member)
        for text, same in by_text.items():
            sources = {m.source_slug for m in same}
            if len(same) > 1:
                kind = "exact_statement" if len(sources) > 1 else "exact_statement_same_source"
                groups.append(
                    DuplicateGroup(
                        group_key=_group_key("exact", code, context_key, language, text),
                        match_type="exact_statement",
                        reason=(
                            f"identical {language} statement for {code} in {context_key} "
                            f"reported by {sorted(sources)}"
                        ),
                        members=[m.record_id for m in same],
                        similarity=1.0,
                        canonical=same[0].record_id,
                    )
                )
                stats["exact"] += 1
                _ = kind

        # near duplicates: compare distinct texts pairwise
        distinct = list(by_text.items())
        for (text_a, group_a), (text_b, group_b) in combinations(distinct, 2):
            score = statement_similarity(group_a[0].definition, group_b[0].definition)
            if rules.similarity_threshold <= score < 1.0:
                groups.append(
                    DuplicateGroup(
                        group_key=_group_key("near", code, context_key, language, text_a, text_b),
                        match_type="near_statement",
                        reason=(
                            f"{language} statements for {code} in {context_key} are "
                            f"{score:.2%} similar; kept as separate rows pending review"
                        ),
                        members=[group_a[0].record_id, group_b[0].record_id],
                        similarity=score,
                        canonical=max(group_a[0].record_id, group_b[0].record_id),
                    )
                )
                stats["near"] += 1

    if include_context_variants:
        by_code: dict[str, set[str]] = defaultdict(set)
        for record in records:
            by_code[record.code].add(record.context_key)
        for code, contexts in sorted(by_code.items()):
            if len(contexts) > 1:
                groups.append(
                    DuplicateGroup(
                        group_key=_group_key("contexts", code),
                        match_type="code_context_variants",
                        reason=(
                            f"{code} is defined in {len(contexts)} contexts; these are different "
                            "meanings and must not be merged"
                        ),
                        members=sorted(contexts),
                        similarity=None,
                        canonical=None,
                    )
                )
                stats["context_variants"] += 1

    return groups, stats
