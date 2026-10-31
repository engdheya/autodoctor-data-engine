"""Conflict detection.

The engine never picks a winner. When two sources disagree about the same
(code, context, language) it keeps both statements, marks both definitions as
``conflicting`` and writes a conflict row with the evidence attached so a human
can review it.

Only statements in the *same* context are compared. P1690 at Ford and P1690 at
BMW are different facts, not a conflict - that is the whole reason ``code`` is not
a unique key in this database.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

from ..config import Rules
from ..identity import definition_content_hash, statement_similarity, statement_text
from ..models import NormalizedDtc


@dataclass
class ConflictEvidence:
    source_slug: str
    source_record_id: str
    value: str
    content_hash: str | None = None
    data_version: str | None = None
    dtc_code_key: str | None = None
    language: str | None = None

    def to_dict(self) -> dict:
        return {
            "source_slug": self.source_slug,
            "source_record_id": self.source_record_id,
            "value": self.value,
            "content_hash": self.content_hash,
            "data_version": self.data_version,
            "dtc_code_key": self.dtc_code_key,
            "language": self.language,
        }


@dataclass
class Conflict:
    conflict_type: str
    code: str
    context_key: str
    attribute: str
    summary: str
    evidence: list[ConflictEvidence] = field(default_factory=list)
    similarity: float | None = None

    def to_dict(self) -> dict:
        return {
            "conflict_type": self.conflict_type,
            "code": self.code,
            "context_key": self.context_key,
            "attribute": self.attribute,
            "summary": self.summary,
            "similarity": self.similarity,
            "evidence": [e.to_dict() for e in self.evidence],
        }


def _source_record(record: NormalizedDtc) -> str:
    return record.provenance.source_record_id


def _version(record: NormalizedDtc) -> str:
    return f"{record.provenance.source_slug}@{record.provenance.source_commit}"


def _cluster_statements(members, threshold: float) -> list[list[tuple]]:
    """Greedy clustering: statements describing the same thing land together."""
    clusters: list[list[tuple]] = []
    for member in members:
        for cluster in clusters:
            if statement_similarity(member[1], cluster[0][1]) >= threshold:
                cluster.append(member)
                break
        else:
            clusters.append([member])
    return clusters


def detect_conflicts(records: list[NormalizedDtc], rules: Rules) -> tuple[list[Conflict], dict[str, int]]:
    conflicts: list[Conflict] = []
    stats = defaultdict(int)

    by_bucket: dict[tuple[str, str, str], list[tuple[NormalizedDtc, Any, str]]] = defaultdict(list)
    for record in records:
        for definition in record.definitions:
            text = statement_text(definition.title, definition.description)
            if not text:
                continue
            by_bucket[(record.code, record.context_key, definition.language)].append(
                (record, definition, text)
            )

    for (code, context_key, language), members in sorted(by_bucket.items()):
        clusters = _cluster_statements(members, rules.similarity_threshold)
        if len(clusters) < 2:
            continue
        sources_involved = {
            member[0].provenance.source_slug for cluster in clusters for member in cluster
        }
        if len(sources_involved) < 2:
            # one source contradicting itself is a data smell, not a source conflict
            stats["same_source_variants"] += len(clusters) - 1
            continue

        # one conflict row per (code, context, language) - reviewers see all
        # competing statements side by side instead of a pair matrix
        worst = 0.0
        for cluster_a, cluster_b in combinations(clusters, 2):
            worst = max(worst, statement_similarity(cluster_a[0][1], cluster_b[0][1]))
        evidence = []
        for cluster in clusters:
            record, definition, text = cluster[0]
            evidence.append(
                ConflictEvidence(
                    source_slug=record.provenance.source_slug,
                    source_record_id=_source_record(record),
                    value=text,
                    content_hash=definition_content_hash(
                        definition.title, definition.description
                    ),
                    data_version=_version(record),
                    dtc_code_key=context_key,
                    language=language,
                )
            )
        conflicts.append(
            Conflict(
                conflict_type="definition_disagreement",
                code=code,
                context_key=context_key,
                attribute=f"definition.{language}",
                summary=(
                    f"{len(clusters)} incompatible {language} descriptions of {code} in "
                    f"{context_key} from {sorted(sources_involved)} "
                    f"(closest pair {worst:.0%} similar)"
                ),
                similarity=round(worst, 4),
                evidence=evidence,
            )
        )
        stats["definition_disagreement"] += 1

    # cause likelihood disagreement -----------------------------------------
    cause_map: dict[tuple[str, str, str], dict[str, list[tuple[NormalizedDtc, str]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for record in records:
        for cause in record.causes:
            if cause.likelihood:
                cause_map[(record.code, record.context_key, cause.key)][cause.likelihood].append(
                    (record, cause.likelihood)
                )
    for (code, context_key, cause_key), by_likelihood in sorted(cause_map.items()):
        if len(by_likelihood) < 2:
            continue
        evidence = []
        for likelihood, items in by_likelihood.items():
            record = items[0][0]
            evidence.append(
                ConflictEvidence(
                    source_slug=record.provenance.source_slug,
                    source_record_id=_source_record(record),
                    value=likelihood,
                    data_version=_version(record),
                    dtc_code_key=context_key,
                )
            )
        conflicts.append(
            Conflict(
                conflict_type="cause_likelihood_disagreement",
                code=code,
                context_key=context_key,
                attribute=f"cause.{cause_key}.likelihood",
                summary=(
                    f"sources disagree on the likelihood of cause {cause_key!r} for {code}: "
                    + ", ".join(sorted(by_likelihood))
                ),
                evidence=evidence,
                similarity=None,
            )
        )
        stats["cause_likelihood_disagreement"] += 1

    # flag disagreement ------------------------------------------------------
    flags_by_code: dict[str, dict[str, list[tuple[str, str]]]] = defaultdict(lambda: defaultdict(list))
    for record in records:
        flags = record.flags
        for name, value in (
            ("mil", flags.mil),
            ("emissions_relevant", flags.emissions_relevant),
            ("limp_mode_possible", flags.limp_mode_possible),
            ("drive_cycle_required", flags.drive_cycle_required),
        ):
            if value is not None:
                flags_by_code[record.context_key][name].append(
                    (record.provenance.source_slug, str(value))
                )
    for context_key, per_flag in flags_by_code.items():
        for name, values in per_flag.items():
            distinct_sources = {src for src, _ in values}
            distinct_values = {val for _, val in values}
            if len(distinct_sources) > 1 and len(distinct_values) > 1:
                code = context_key.split("|")[0]
                conflicts.append(
                    Conflict(
                        conflict_type="flag_disagreement",
                        code=code,
                        context_key=context_key,
                        attribute=f"flags.{name}",
                        summary=f"sources disagree on flag {name} for {code}: "
                        + ", ".join(f"{s}={v}" for s, v in sorted(set(values))),
                        evidence=[
                            ConflictEvidence(
                                source_slug=src,
                                source_record_id=context_key,
                                value=val,
                                dtc_code_key=context_key,
                            )
                            for src, val in sorted(set(values))
                        ],
                    )
                )
                stats["flag_disagreement"] += 1

    return conflicts, dict(stats)
