# Conflict review

The engine never decides which source is right. It stores the disagreement, keeps both statements,
and hands the decision to a human — once.

## The problem this solves

A rebuild recreates every conflict row, so a decision made by hand would be lost, and the same 4,435
conflicts would be reviewed again next week. Conflicts are therefore keyed by a **content
fingerprint**, and decisions are stored in `data/reviews/conflicts.yaml`, which is committed.

```
conflict ──fingerprint──► decision (data/reviews/conflicts.yaml) ──► next build applies it
```

## Fingerprint

```
sha256("1 | <conflict_type> | <context_key> | <attribute> | <sorted slug:content_hash>")[:16]
```

* independent of database ids, which change on every build;
* independent of statement *length* (the content hash is what deduplication already uses);
* **dependent on the wording**: if an upstream rewrites a statement, the fingerprint changes and the
  conflict needs a fresh review. A decision is never stretched over new text.

## Workflow

```console
$ autodoctor list-conflicts --limit 2          # against the public build (503 open)
conflicts: 503 open, 0 resolved, 0 accepted differences

B0003  [B0003|sae_j2012|generic:generic]  definition_disagreement
  fingerprint: ca9d218b27127b54
  status:      needs_review
  summary:     2 incompatible en descriptions of B0003 in B0003|sae_j2012|generic:generic
               from ['obdex', 'wal33d'] (closest pair 63% similar)
    <- obdex      Driver Frontal Deployment Loop Resistance Low — The SRS module has detected…
    <- wal33d     Driver Frontal Stage 3 Deployment Control
```

Two ways to close it, and nothing in between:

```console
# 1. both statements are legitimate (wording variants, market differences)
$ autodoctor review-conflict ca9d218b27127b54 --accept \
    --note "OBDex describes the loop, Wal33D the deployment stage; not contradictory" \
    --reviewer "qa-lead"
recorded accepted_difference for ca9d218b27127b54 (qa-lead)
stored in data/reviews/conflicts.yaml

# 2. one statement is wrong; name the one to keep
$ autodoctor review-conflict ca9d218b27127b54 --resolve --source obdex \
    --note "the SRS deployment-loop statement is the one the OEM manual uses" \
    --reviewer "qa-lead"
```

A `resolved` decision also makes the chosen statement the **canonical** one for that
(code, language) — the only way a human decision changes content in this engine.

## What the build does with a decision

| Decision | Effect on `conflicts` | Effect on content |
| --- | --- | --- |
| `accepted_difference` | `status = 'accepted_difference'`, `resolution_note` = decision + reviewer + date | none; both statements stay, both keep `conflicting` |
| `resolved --source X` | `status = 'resolved'`, note records the choice | the statement claimed by X becomes `is_canonical = 1` for that language |

Counts follow: `conflicts_open` counts `needs_review` only, `conflicts_resolved` counts the rest.
`build-db` prints both, and the manifest stores them.

If a stored decision no longer matches any conflict (the source dropped the statement, or the wording
changed), the build reports it in `review_stats.unmatched` and carries on — a decision is never
applied to different text.

## File format

```yaml
version: 1
decisions:
  - fingerprint: ca9d218b27127b54
    decision: accepted_difference
    note: OBDex describes the loop, Wal33D the deployment stage; not contradictory
    reviewer: qa-lead
    decided_at: '2026-10-31T22:10:11Z'
    code: B0003
    context_key: B0003|sae_j2012|generic:generic
    conflict_type: definition_disagreement
```

The file is validated on load: a decision without a note, a reviewer, or (for `resolved`) a chosen
source is rejected by the CLI with a non-zero exit code.

## Tests

`tests/test_reviews.py` (11 tests) covers: fingerprint stability across rebuilds and uniqueness,
store validation rules, write/read round-trip, a decision closing the conflict *and surviving the
next rebuild*, the canonical override, unmatched decisions, and the CLI round-trip.

## Still to build (phase 2)

* a review UI/CSV export for batch work (`autodoctor list-conflicts --json` already feeds one);
* a policy for *who* may resolve what, and an audit export per release;
* per-source-pair statistics so the 4,435 open conflicts can be triaged by value instead of by code.
