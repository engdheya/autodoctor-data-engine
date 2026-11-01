# Phase 1 delivery report

**AutoDoctor Data Integration Engine · engine 0.1.0 · database 0.4.0 · 2026-11-01**

Every number in this report was read from the built databases, the release manifests, the staging
manifests or the test runner. Nothing is estimated. Where the first draft of this report carried a
stale figure, the correction is listed in [§13](#13-corrections-against-the-first-draft-of-this-report).

## ملخّص بالعربية

تم بناء محرّك البيانات وربطه بأربعة مصادر حقيقية، وخرجت نسختان من قاعدة البيانات من نفس الكود:

* **نسخة خاصة (private)**: 40,222 هوية كود عطل (19,216 كودًا مختلفًا)، 65,108 تعريفًا،
  14,029 تعريفًا مؤكَّدًا من مصدرين مستقلَّين، 352,761 سجل مصدر، 4,435 تعارضًا موثّقًا — للمراجعة الداخلية.
* **نسخة عامة (public)**: 19,089 هوية كود (12,412 كودًا)، 37,871 تعريفًا، 233,432 سجل مصدر،
  503 تعارضات — **لا تحتوي أي بيانات من autodiag2 أو OBDb** لأن مراجعتهما القانونية لم تكتمل،
  والمنع مفروض في الكود (`--source-set public` + البوابة `D011`) وليس مجرّد توثيق.
* **210 اختبارًا آليًا**: 205 ناجحة في 2.35 ثانية، و5 اختبارات تكامل حقيقية ناجحة أيضًا على
  المستودعات الفعلية (48.71 ثانية) عند تفعيلها.
* **أداة مراجعة تعارضات**: لكل تعارض بصمة ثابتة وقرار بشري محفوظ في `data/reviews/conflicts.yaml`،
  فلا يُطرح التعارض المحلول مرة أخرى بعد إعادة البناء.
* **مثال عملي كامل** لكود P0301 من الاستيراد إلى العرض — في [EXAMPLE_P0301](EXAMPLE_P0301.md).

لا توجد ترجمة عربية ولا إجراءات فحص جاهزة، لأن المصادر لا توفّر أيًّا منهما، والمحرّك يرفض
الترجمة الآلية واختراع الإجراءات. خطتهما مكتوبتان في [PHASE2_TRANSLATION_PLAN](PHASE2_TRANSLATION_PLAN.md)
و[PHASE2_DTC_PROCEDURES_PLAN](PHASE2_DTC_PROCEDURES_PLAN.md).

---

## 1. What was built

| Component | Detail |
| --- | --- |
| Source registry | `config/sources.yaml` — 4 sources with code licence, data licence, lineage, scope, legal-review status |
| Connectors | OBDex (YAML families), Wal33D (SQLite + text lists), autodiag2 (28,833 YAML files), OBDb (multi-repo JSON signal sets) |
| Parsers | YAML (incl. multi-document), JSON, read-only SQLite, delimited text |
| Normalizers | codes, text (NFC/whitespace), languages, manufacturer aliases, stable concept keys, contextual identity keys |
| Validation | 15 record rules (`V001`–`V014`, `V020`) + 11 database release gates (`D001`–`D011`) |
| Deduplication | exact (canonical headline), near (similarity), code-context variants — three distinct verdicts |
| Conflicts | cross-lineage disagreement only; one conflict per `(code, context, language)` with evidence |
| Review tool | stable conflict fingerprints, `list-conflicts` / `review-conflict`, decisions persisted in `data/reviews/conflicts.yaml` |
| Merge | provenance-first loader, deterministic canonical choice, lineage-based verification, derived risk rule |
| Publication | two editions (`--source-set public\|private`), SQLite build, export, app bundle, manifest with SHA-256, `db_versions` row |
| Reporting | import report, data report (markdown + JSON), change detection, source inspection |
| CLI | 17 commands |
| Tests | 210 (205 offline + 5 real-source integration) |
| CI | lint + tests on Python 3.11/3.12/3.13, docs/CLI check, weekly upstream-drift workflow — kept in `ci/` because the pushing GitHub App lacks the `workflows` permission; one `cp` activates them |

## 2. The seven acceptance requirements

| # | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Real public/private separation, enforced in code and tested | **done** | `config.SOURCE_SETS` + `resolve_source_set`; `build-db/run-all --source-set`; gate `D011` blocks any fact from an unapproved source in a public build; `assert_public_safe()` in the app-bundle builder; `tests/test_publication.py` (12 tests) |
| 2 | Review `app_export.py` and `D007` so nothing unapproved leaks | **done** | the bundle builder re-checks the source set before writing; both published bundles were compared table by table against the private one (see [PUBLICATION](PUBLICATION.md)) |
| 3 | Run the integration tests against the real upstream repositories | **done** | 5/5 passed in 48.71 s — [INTEGRATION_RESULTS](INTEGRATION_RESULTS.md) |
| 4 | Review every number in `README.md` and this report | **done** | all tables regenerated from the 0.4.0 manifests and databases; corrections listed in §12 |
| 5 | Phase-2 plan for reviewed Arabic + inspection procedures | **done** | [PHASE2_TRANSLATION_PLAN](PHASE2_TRANSLATION_PLAN.md), [PHASE2_DTC_PROCEDURES_PLAN](PHASE2_DTC_PROCEDURES_PLAN.md) |
| 6 | Conflict review tool that persists decisions | **done** | `autodoctor list-conflicts`, `autodoctor review-conflict`, `data/reviews/conflicts.yaml`, `tests/test_reviews.py` (11 tests) + [CONFLICT_REVIEW](CONFLICT_REVIEW.md) |
| 7 | Documented P0301 example from import to SQLite | **done** | [EXAMPLE_P0301](EXAMPLE_P0301.md) + `data/samples/autodoctor-sample.sqlite` (runnable) |

## 3. Files created (cumulative)

```
config/sources.yaml                     db/schema.sql (521 lines, schema v3)
docs/ARCHITECTURE.md                    docs/DATABASE_SCHEMA.md
docs/DATA_SOURCES.md                    docs/LICENSES.md
docs/DATA_DICTIONARY.md                 docs/DEVELOPMENT_PLAN.md
docs/FLUTTER_INTEGRATION.md             docs/PHASE1_REPORT.md
docs/PUBLICATION.md                     docs/EXAMPLE_P0301.md
docs/CONFLICT_REVIEW.md                 docs/INTEGRATION_RESULTS.md
docs/PHASE2_TRANSLATION_PLAN.md         docs/PHASE2_DTC_PROCEDURES_PLAN.md
README.md  THIRD_PARTY_NOTICES.md  LICENSE  .env.example  .gitignore
ci/ci.yml                               ci/upstream-drift.yml  ci/README.md
data/reviews/conflicts.yaml             data/translations/{README.md,ar/example.yaml}
scripts/build_sample_db.py              data/samples/autodoctor-sample.sqlite
src/autodoctor_data_engine/**
  config.py  models.py  pipeline.py  staging.py  cli.py  identity.py  translations.py  reviews.py
  provenance/tracker.py
  connectors/{base,obdex,wal33d,autodiag,obdb,__init__}.py
  parsers/{yaml_loader,json_loader,sqlite_reader,delimited}.py
  normalizers/{codes,text,languages,manufacturers,keys}.py
  validators/{rules,database,database_rules}.py
  deduplication/detector.py             conflict_resolution/detector.py
  merger/{loader,repository}.py         versioning/{semver,manifest}.py
  database/{connection,schema,repository,build,app_export}.py
  reporting/{import_report,data_report,changes}.py     utils/{hashing,jsonl,textsim,logging}.py
tests/**  (16 test modules + fixtures for all four sources)
```

## 4. Sources inspected (measured against the real repositories)

| Source | Commit | Files | Data licence | Review | Layout |
| --- | --- | ---: | --- | --- | --- |
| OBDex | `a9d0220bdb99…` | 17 | CC0-1.0 | approved | 9,533 entries, 13 keys, 23,364 source URLs, 132 PIDs |
| Wal33D | `04c43d72e7db…` | 38 | MIT | approved | 18,805 rows in SQLite (18,826 parseable text lines) · 12,128 codes · 34 manufacturers |
| autodiag2 | `11e73fd6d105…` | 28,833 | ODbL-1.0 / DbCL-1.0 | **pending** | 28,833 code files · 16,674 codes · 1,516 vehicle files · 1,149 ECU definitions; 27,967 files cite `obdcodex` |
| OBDb | `obdb:bfe465163d…` (5 repos) | 1,198 | CC-BY-SA-4.0 | **pending** | 1,409 signals, 19 ECU entries, **0 DTC definitions** |

## 5. Records imported (private build)

Read from `data/staging/<slug>/<commit>/manifest.json`:

| Source | Raw | Normalized | Rejected | Validation failed / errors | Import time |
| --- | ---: | --- | ---: | --- | ---: |
| obdex | 9,665 | 9,533 dtc + 132 pid | 0 | 25 / 0 | 32.42 s |
| wal33d | 18,805 | 18,805 dtc | 0 | 64 / 0 | 3.30 s |
| autodiag | 31,434 | 28,832 dtc + 1,085 ecu + 1,516 vehicle | **1** (`P15O9`, `V001`) | 5 / 1 | 29.46 s |
| obdb | 1,447 | 1,409 pid + 19 vehicle + 19 ecu | 0 | 0 / 0 | 0.17 s |

**Totals:** 61,351 raw records → 61,350 immutable `source_records` (the quarantined `P15O9` is not
merged), 31,454 `source_files`, **57,170 staged DTC records**. The private database records 808,740
validation results (93 failed: 93 warnings, 0 errors in the merged data).

## 6. The two editions (database 0.4.0, built by `build-db`)

| Metric | Private (4 sources) | Public (2 sources) |
| --- | ---: | ---: |
| Source files / records | 31,454 / 61,350 | 10 / 28,470 |
| DTC identities (code + standard + context) | 40,222 | 19,089 |
| — generic | 12,947 | 9,699 |
| — manufacturer | 26,409 | 9,390 |
| — ECU | 866 | 0 |
| — vehicle-variant | 0 | 0 |
| Distinct codes | 19,216 | 12,412 |
| Definitions | 65,108 (55,575 en · 9,533 de · 0 ar) | 37,871 |
| Verified / source-reported / conflicting | 14,029 / 42,108 / 8,971 | 16,652 / 20,213 / 1,006 |
| Causes · symptoms · repairs · related codes · components | 28,334 · 26,283 · 9,533 · 32,361 · 23,176 | identical |
| Tests (`dtc_tests`) | 0 | 0 |
| PIDs | 1,541 | 132 |
| Manufacturers · ECUs · vehicles · variants | 163 · 1,105 · 1,538 · 24 | 33 · 0 · 0 · 0 |
| Evidence citations (source URLs / references) | 24,183 / 37,546 | 23,364 / 9,580 |
| Provenance claims | 352,761 | 233,432 |
| Open conflicts | 4,435 | 503 |
| Duplicate groups | 14,224 (47,359 members) | 9,587 (24,911 members) |
| Validation results (warnings / errors) | 808,740 (93 / 0) | 396,996 (89 / 0) |
| Release gates passed | 9 / 11 | 11 / 11 |
| Database / app bundle | 169.5 MB / 71.2 MB | 105.8 MB / 52.1 MB |
| Arabic definitions | 0 | 0 |

`P1690` is stored **34 times** (one per manufacturer that documents it) — the proof that `code` is not
a unique key. `P0420` keeps the generic statement and, separately, the manufacturer-specific ones.

The public edition verifies *more* definitions (16,652 vs 14,029) precisely because verification
counts independent lineages: autodiag2 mostly re-reports `obdcodex`, so removing it removes
"corroboration" that was never independent. This was one of the reasons for the public/private split.

## 7. Duplicates

| Kind | Private | Public | What happened |
| --- | ---: | ---: | --- |
| `exact_statement` | 8,573 | 8,326 | merged into one definition row with several provenance claims |
| `near_statement` | 1,465 | 321 | reported only — **both rows kept**, no merging by similarity |
| `code_context_variants` | 4,186 | 940 | reported as *not* duplicates (same code, different context) |
| **Total groups** | **14,224** | **9,587** | stored in `duplicate_groups` / `duplicate_members` |

Identical statements from the same source count as `same_source_variants`: not corroboration, not a
duplicate merge.

## 8. Conflicts and the review workflow

| Metric | Private | Public |
| --- | ---: | ---: |
| Open conflicts (`needs_review`) | 4,435 | 503 |
| Resolved / accepted differences | 0 / 0 | 0 / 0 |
| Type | `definition_disagreement` | `definition_disagreement` |
| Definitions flagged `conflicting` | 8,971 | 1,006 |

```console
$ autodoctor list-conflicts --limit 1
conflicts: 503 open, 0 resolved, 0 accepted differences

B0003  [B0003|sae_j2012|generic:generic]  definition_disagreement
  fingerprint: ca9d218b27127b54
  status:      needs_review
  summary:     2 incompatible en descriptions of B0003 in B0003|sae_j2012|generic:generic
               from ['obdex', 'wal33d'] (closest pair 63% similar)
    <- obdex      Driver Frontal Deployment Loop Resistance Low — …
    <- wal33d     Driver Frontal Stage 3 Deployment Control

$ autodoctor review-conflict ca9d218b27127b54 --accept \
    --note "loop vs stage wording, not contradictory" --reviewer "qa-lead"
recorded accepted_difference for ca9d218b27127b54 (qa-lead)
```

Decisions live in `data/reviews/conflicts.yaml` (committed) and are keyed by a fingerprint over
`(type, context, attribute, sorted slug:content_hash)` — so a rebuild does not re-open a decided
conflict, and a rewritten statement is *not* silently covered by an old decision. See
[CONFLICT_REVIEW](CONFLICT_REVIEW.md).

## 9. Test results (measured 2026-11-01)

```console
$ python -m pytest
205 passed, 5 skipped in 2.35s

$ AUTODOCTOR_INTEGRATION=1 python -m pytest tests/test_integration_real_sources.py -v
5 passed in 48.71s

$ ruff check src tests scripts
All checks passed!
```

| Area | Tests |
| --- | ---: |
| config | 7 |
| parsers | 9 |
| normalizers (codes, text, languages, manufacturers, keys) | 38 |
| connectors (all four sources) | 20 |
| validators (record rules) | 14 |
| deduplication | 6 |
| conflicts | 7 |
| pipeline (raw, staging, quarantine) | 8 |
| database (build 19, queries 8, provenance 6, translations 6, app bundle 7) | 46 |
| publication (public/private set, gates, bundles) | 12 |
| conflict review (fingerprints, store, rebuild) | 11 |
| sample database | 4 |
| CLI | 14 |
| change detection | 3 |
| models | 6 |
| real sources (opt-in, skipped by default) | 5 |
| **Total** | **210** |

## 10. Problems found (and what was done about them)

1. **`dtc_tests` is empty (0 rows).** No upstream supplies procedures; autodiag2's schema fields for
   them are empty in every real record. Table, texts, provenance and validators are implemented and
   tested — content is a phase-2 authoring task with its own plan.
2. **No Arabic (0 rows).** No source contains Arabic. The engine refuses machine translation, accepts
   only reviewed human translations, and ships a CSV template generator plus the loader.
3. **autodiag2's payload is much thinner than its schema.** Only code, definition, created, updated,
   protocol, standard and evidence are ever populated. The connector takes exactly those.
4. **autodiag2 and OBDb are share-alike and unreviewed.** They are excluded from the public edition by
   `--source-set public`; `D007` reports it, `D011` blocks it. Public distribution is safe today.
5. **Wal33D's compiled SQLite does not match its shipped text lists** (18,805 vs 18,826). Recorded as
   an inspection warning; the compiled database is imported because it is the structured artifact.
6. **`evidence` is not independence.** 27,967 autodiag2 files cite `obdcodex`; corroboration counts
   lineages, so autodiag2 alone never verifies anything.
7. **Real data smells, not bugs:** `dtc_repairs` (9,533) equals the OBDex code count because only OBDex
   has repair data; `manufacturers` includes an `Unspecified` bucket from Wal33D's `OTHER` label —
   kept and documented rather than discarded.
8. **One invalid upstream code** (`P15O9`, letter O) is quarantined, not silently repaired.
9. **App bundle size.** 71.2 MB private / 52.1 MB public, after dropping the claim matrix. Acceptable
   for the first release; a "lite" variant is a phase-2 option.
10. **`P1690`-style ambiguity is the norm:** 198 Wal33D codes are both generic and
    manufacturer-specific. The UI must always show which context is displayed.
11. **The app bundle could silently lose its views — twice, for two different reasons.**
    The bundle is built in WAL mode; the connection stayed open while a second connection
    vacuumed the file, and its late checkpoint could overwrite the vacuumed image with a page
    cache that predated the `CREATE VIEW` statements. Separately, `scripts/build_sample_db.py`
    attached the *published* bundle and issued an unqualified `DROP VIEW`/`CREATE VIEW`, which
    could strip the source bundle of a view while the sample itself looked fine. Both are fixed
    (explicit `PRAGMA wal_checkpoint(TRUNCATE)` + close before the vacuum; the source is now
    attached `?mode=ro` and views are created `main.`-qualified after detach) and both are now
    *detected*: `_verify_views()` re-opens the finished artifact, fails the build if
    `v_dtc_lookup`/`v_dtc_summary` are missing, and deletes the bad file. Regression tests cover
    the missing-view case and assert that sampling never modifies the published bundle. The four
    published artifacts were then re-verified: views present, `sha256` equal to the manifest.
12. **Code-level status was wrong.** A `dtc_code` claim now aggregates its statements
    (verified > conflicting > all-unverified ⇒ unverified), so `search` no longer shows a code as
    verified while its only statement is conflicting.

## 11. Next step

Phase 2, in this order (see [DEVELOPMENT_PLAN](DEVELOPMENT_PLAN.md)):

1. Close the licence review for autodiag2/OBDb. Until then the public edition stays OBDex + Wal33D.
2. Arabic programme on the generic layer, glossary first — [PHASE2_TRANSLATION_PLAN](PHASE2_TRANSLATION_PLAN.md).
3. 20 verified inspection procedures for the highest-risk generic codes — [PHASE2_DTC_PROCEDURES_PLAN](PHASE2_DTC_PROCEDURES_PLAN.md).
4. Work down the conflict queue with the review tool; target the generic layer first (503 public).
5. Activate the CI workflows and let `upstream-drift` open issues automatically.

Flutter work still does not start here: the user's condition — data integrity, licences and database
quality confirmed — is met for the public edition (11/11 gates) and the remaining content gaps
(Arabic, procedures) are content, not structure.

## 12. Deliverables in this hand-off

Everything below is committed or generated by the commands shown; the sizes and hashes were
re-read after the last build (2026-11-01) and match their manifests.

| Artifact | Size | SHA-256 | Runnable |
| --- | ---: | --- | --- |
| `data/samples/autodoctor-sample.sqlite` | 1.6 MB | `51be347b1f2f…` | **yes** — 300 generic codes, views included |
| `db/autodoctor.sqlite` | 105.8 MB | `4cd5df24b2ed…` | **yes** — copy of the public edition |
| `data/exports/autodoctor-0.4.0-public.sqlite` + `.manifest.json` | 105.8 MB | `4cd5df24b2ed…` | yes |
| `data/exports/autodoctor-app-0.4.0-public.sqlite` | 52.1 MB | `00d1003a140e…` | yes — the file Flutter ships |
| `data/exports/autodoctor-0.4.0.sqlite` + `.manifest.json` | 169.5 MB | `3ad23e13596e…` | internal only (pending sources inside) |
| `data/exports/autodoctor-app-0.4.0.sqlite` | 71.2 MB | `899df14827ba…` | internal only |

```console
$ autodoctor search P0301            # against db/autodoctor.sqlite
P0301  [generic]
  EN: Cylinder 1 Misfire Detected
  causes: 5  symptoms: 4  tests: 0  repairs: 1  sources: 2
  risk: high
```

Code and tests: `src/autodoctor_data_engine/**`, `scripts/build_sample_db.py`,
`tests/**` (210 tests). Documents: the seven phase-1 documents plus
[PUBLICATION](PUBLICATION.md), [EXAMPLE_P0301](EXAMPLE_P0301.md), [CONFLICT_REVIEW](CONFLICT_REVIEW.md),
[INTEGRATION_RESULTS](INTEGRATION_RESULTS.md) and the two phase-2 plans.

**Reproduce from scratch:**

```bash
pip install -e ".[dev]"
autodoctor fetch-sources
autodoctor import --all
autodoctor build-db --version 0.4.0 --source-set public
python scripts/build_sample_db.py \
    --source data/exports/autodoctor-app-0.4.0-public.sqlite \
    --out data/samples/autodoctor-sample.sqlite --limit 300
```

## 13. Corrections against the first draft of this report

The first draft was written against an earlier build and carried several stale or wrong figures. All
of them were re-derived from the 0.4.0 artifacts:

| Claim in the first draft | Measured | Why it was wrong |
| --- | --- | --- |
| "178 automated tests" (and 177 in the README) | 205 pass + 5 skipped = 210 | the suite grew with publication, review and sample tests |
| "9/10 release gates" | 11 gates, 9/11 private, 11/11 public | `D011` was added and `D007` re-scoped |
| "Autodiag 30,075 raw / 28,832 dtc" | 31,434 raw / 28,832 dtc | the connector now keeps the vehicle and ECU records it used to drop |
| "OBDb 590 raw, 1 repo, 580 signals" | 1,447 raw, 5 repos, 1,409 signals | OBDb is an org; `fetch-sources` now clones five vehicle repositories |
| "manufacturers 41 · ECUs 1,088 · vehicles 166 · variants 9" | 163 · 1,105 · 1,538 · 24 | manufacturer aliasing was completed; vehicle metadata files are imported |
| "PIDs 712" (README) | 1,541 private / 132 public | 712 matched neither edition |
| "327,369 provenance claims" (README) | 352,761 private / 233,432 public | stale build |
| "60 MB bundle / 147 MB database" | 71.2 MB / 169.5 MB private, 52.1 MB / 105.8 MB public | bundle shrank later only because the claim matrix was dropped |
| "4 integration tests" | 5 | the public source-set test was added |
| "`P1690` stored 22 times" | 34 identities | the 0.1.0 build saw fewer manufacturer tables |
| "57,170 staged DTC records" | 57,170 ✔ (unchanged) | — |
| "two editions do not exist yet" (§10 of the draft) | they do | the draft's action list is now §11 |

Any number not listed above was already correct and is reproduced here from the same artifacts.
