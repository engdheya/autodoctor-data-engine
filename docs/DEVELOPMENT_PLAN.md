# Development plan

AutoDoctor AI is built in phases so that data quality is proven before any product surface depends
on it. This document is the plan of record; status is updated as phases close.

## Phase 1 — Data integration engine ✅ done

**Goal:** read real sources, keep the raw data, normalize, deduplicate, store provenance, build one
validated SQLite database, prove it with tests, publish a versioned release.

| Deliverable | State |
| --- | --- |
| Source registry with licence records | ✅ `config/sources.yaml` |
| Connectors for OBDex, Wal33D, autodiag2, OBDb | ✅ |
| Immutable raw archive per commit | ✅ `data/raw/<slug>/<commit>/*.jsonl` |
| Normalization (codes, text, languages, manufacturers, keys) | ✅ |
| Context-aware identity (`code` is not unique) | ✅ 40,222 identities / 19,216 codes |
| Deduplication (exact / near / context variants) | ✅ 8,573 / 1,465 / 4,186 |
| Conflict detection with evidence | ✅ 4,435 open conflicts |
| Provenance claim per statement | ✅ 327,369 claims |
| Validation: 20 record rules + 10 release gates | ✅ |
| Merge + canonical selection + verification | ✅ 14,029 verified statements |
| SQLite build + app bundle + manifest + SHA-256 | ✅ 147 MB / 60 MB |
| CLI (15 commands) | ✅ |
| Tests | ✅ 177 (173 offline + 4 integration) |
| Documentation (7 documents) | ✅ |
| CI | ✅ `.github/workflows/ci.yml` |
| Arabic content | ⛔ not available from any source; pipeline ready, content pending |
| Inspection procedures (`dtc_tests`) | ⛔ no source provides them; pipeline ready |

**Measured outcome:** 0.1.0 builds and passes 9/10 release gates, the tenth being the licence
review (see [LICENSES](LICENSES.md)).

## Phase 2 — Data quality and coverage (next)

Ordered by value per unit of risk:

1. **Licence review of autodiag2 and OBDb.** Needed before anything is public. Then split the
   app bundle into `--source-set private` / `public` and make `D007` blocking for the public one.
2. **Arabic translation programme.** `export-translation-template` → translator batches →
   `data/translations/ar/` → rebuild. Priority order: the 2,000 most-read codes (generic layer,
   MIL-relevant), then manufacturer codes. Target: 100 % of the generic layer reviewed.
3. **Inspection procedures.** Author `dtc_tests` content for the generic layer (measurement,
   freeze-frame, expected values, required tool). This is the difference between "a code means X"
   and "here is how you check X", which is the product's value.
4. **Conflict review workflow.** 4,435 conflicts need a decision. Build a review CLI
   (`autodoctor review conflicts --status`) that writes `accepted_difference`/`resolved` with a
   note, and make the next build carry those decisions instead of re-raising them.
5. **More sources** (each needs a licence entry first): manufacturer service data with an
   explicit redistribution grant, ISO 15031-6 reference tables for canonical generic wording,
   and additional OBDb vehicle repositories for parameter coverage.
6. **Data freshness.** Scheduled CI job: fetch → import → `detect-changes` → open an issue with the
   diff when a source moves. Vanished records are reported, never deleted (already implemented in
   `detect-changes`).
7. **Payload pruning.** `manifest.json` and the app bundle carry `fmt_json`/`notes` that are useful
   for engineering only; a second, smaller "lite" bundle (target < 25 MB) makes the first-run
   download pleasant on mobile data.
8. **Performance.** `v_dtc_summary` uses correlated subqueries; at 40k identities this is fine on
   desktop but should be materialized (or replaced by a precomputed table) for the app.

## Phase 3 — Flutter application

Rules that come from phase 1 and are not negotiable:

* offline-first: the app ships `autodoctor-app-<v>.sqlite`, has no mandatory backend;
* the diagnostic card shows **what the code means, what to check first, what it does not mean**;
* the UI must render `verification_status` and conflicts — a "sources disagree" state is a feature,
  never hidden behind a single string;
* bilingual from day one: `title_en` and `title_ar` side by side, locale-aware fallback;
* updates: download the next app bundle, verify SHA-256, swap the file, keep the previous version
  for rollback.

## Phase 4 — Diagnostics assistance

Only after phases 2–3: guided tests (using `dtc_tests`), symptom→cause ranking **displayed as
possibilities with their source and likelihood**, and a history of the user's own scans. No
automatic diagnosis and no "replace this part" advice without an inspection step.

## Engineering conventions

* Python 3.11+, `pytest`, `ruff`; minimal dependencies (pydantic, pyyaml; sqlalchemy optional).
* `pytest` must be green before any merge; CI runs ruff + pytest + a fixture build.
* Commits are scoped: `feat(connectors):`, `fix(merger):`, `docs:`, `test:`, `chore:`.
* Generated data (`db/`, `data/`) never enters git; releases are artifacts, not commits.
* Every schema change is additive and lands with its migration note in `db/schema.sql` plus a test.

## Risks

| Risk | Mitigation |
| --- | --- |
| Upstream licence change or withdrawal | commit pinned, hashes stored, `detect-changes` reports it, sources are excluded by flag — not by editing history |
| Data drift making builds non-reproducible | manifest stores commits + per-file SHA-256 + content hash |
| Share-alike obligations misread | `legal_review_status` gate; public bundle limited to CC0 + MIT until review closes |
| Over-merging distinct codes | context key, no similarity merging, 4,186 reported context variants, tests that assert P1690 stays two identities |
| Empty research fields mistaken for "no problem" | `NULL` instead of invented values; validators warn; docs state the gaps explicitly |
