# Phase 1 delivery report

**AutoDoctor Data Integration Engine · version 0.1.0 · 2026-10-31**

Every number in this report was read from the built database, the staging manifests or the test
runner. Nothing is estimated.

## ملخّص بالعربية

تم بناء محرّك البيانات بالكامل وربطه بأربعة مصادر حقيقية، وخرجت نسخة `0.1.0` قابلة للنشر:

* **57,170** سجل كود عطل بعد التوحيد، تمثّل **19,216** كودًا مختلفًا و**40,222** هوية (كود + سياق).
* **65,108** تعريفًا (إنجليزي/ألماني)، منها **14,029** مؤكَّد من مصدرين مستقلَّين على الأقل.
* **327,369** سجل مصدر (Provenance) يربط كل معلومة بالمستودع والـ commit والملف والسجل والترخيص.
* **4,435** تعارضًا موثّقًا بين المصادر، محفوظة جميعها للمراجعة البشرية دون حذف أي رأي.
* **178** اختبارًا آليًا كلها ناجحة، و**9/10** بوابات جودة مُجتازة (البوابة العاشرة هي مراجعة الترخيص).
* لا توجد ترجمة عربية جاهزة لأن أيًّا من المصادر لا يوفّرها؛ المحرّك يرفض الترجمة الآلية ويقبل فقط
  ترجمة بشرية مراجَعة، وأداة القالب جاهزة.
* لا توجد إجراءات فحص (tests) لأن المصادر لا توفّرها؛ الجدول والمسار جاهزان والبيانات هي المطلوبة.

المطلوب للموافقة قبل الانتقال إلى المرحلة الثانية: هيكل المشروع، خطة الدمج، قرار نشر المستودع،
ومعالجة الترخيص (انظر نهاية التقرير).

---

## 1. What was implemented

| Component | Detail |
| --- | --- |
| Source registry | `config/sources.yaml` — 4 sources with code/data licences, lineage, scope, legal review |
| Connectors | OBDex (YAML families), Wal33D (SQLite + text lists), autodiag2 (28 833 YAML files), OBDb (multi-repo JSON signal sets) |
| Parsers | YAML (incl. multi-document), JSON, read-only SQLite, delimited text |
| Normalizers | codes, text (NFC/whitespace), languages, manufacturer aliases, stable concept keys, contextual identity keys |
| Validation | 15 record rules (`V001`–`V014`, `V020`), 4 blocking, plus 10 database release gates (`D001`–`D010`) |
| Deduplication | exact (canonical headline), near (similarity), code-context variants — three distinct verdicts |
| Conflict resolution | cross-lineage disagreements only; one conflict per `(code, context, language)` with evidence |
| Merge | provenance-first loader, deterministic canonical choice, lineage-based verification, derived risk rule |
| Publication | SQLite build, engineering export, 60 MB Flutter bundle, manifest with SHA-256, `db_versions` row |
| Reporting | import report, data report (markdown + JSON), change detection between builds, source inspection |
| CLI | 15 commands (`inspect-sources`, `fetch-sources`, `import`, `validate`, `detect-duplicates`, `detect-conflicts`, `build-db`, `report`, `search`, `explain`, `detect-changes`, `export-translation-template`, `version`, `run-all`) |
| Tests | 177 (173 offline + 4 real-source integration) |
| CI | lint + tests on Python 3.11/3.12/3.13, docs/CLI check, weekly upstream-drift workflow |

## 2. Files created

```
config/sources.yaml                     db/schema.sql (513 lines)
docs/ARCHITECTURE.md                    docs/DATABASE_SCHEMA.md
docs/DATA_SOURCES.md                    docs/LICENSES.md
docs/DATA_DICTIONARY.md                 docs/DEVELOPMENT_PLAN.md
docs/FLUTTER_INTEGRATION.md             docs/PHASE1_REPORT.md
README.md  THIRD_PARTY_NOTICES.md  LICENSE  .env.example  .gitignore
.github/workflows/ci.yml                .github/workflows/upstream-drift.yml
data/translations/README.md             data/translations/ar/example.yaml
src/autodoctor_data_engine/**
  config.py  models.py  pipeline.py  cli.py  identity.py  translations.py  provenance.py
  connectors/{base,obdex,wal33d,autodiag,obdb,__init__}.py
  parsers/{yaml_loader,json_loader,sqlite_reader,delimited}.py
  normalizers/{codes,text,languages,manufacturers,keys}.py
  validators/{rules,database}.py
  deduplication/detector.py             conflict_resolution/detector.py
  merger/{loader,repository}.py         versioning/{semver,manifest}.py
  database/{connection,schema,repository,build,app_export}.py
  reporting/{import_report,data_report,changes}.py     utils/{hashing,jsonl,textsim,logging}.py
tests/**  (11 test modules over 5 directories + fixtures for all four sources)
```

## 3. Sources inspected (measured)

| Source | Commit | Files | Data licence | Review | Layout observations |
| --- | --- | ---: | --- | --- | --- |
| OBDex | `a9d0220bdb99…` | 17 | CC0-1.0 | approved | 9,533 entries, 13 keys, 23,364 source URLs, 132 PIDs |
| Wal33D | `04c43d72e7db…` | 38 | MIT | approved | 18,805 rows in SQLite, but the shipped text lists hold 18,826 parseable lines — the compiled database is not reproducible from them |
| autodiag2 | `11e73fd6d105…` | 28,833 | ODbL-1.0 / DbCL-1.0 | **pending** | only 7 of its schema keys are ever populated; 27,967 files cite `obdcodex` as evidence |
| OBDb | `obdb:662b317e…` (1 repo) | 1,198 | CC-BY-SA-4.0 | **pending** | 580 signals, 8 ECU entries, **0 DTC definitions** |

## 4. Records imported

| Source | Raw records | Staged | Rejected | Validation warnings | Duration |
| --- | ---: | --- | ---: | --- | ---: |
| obdex | 9,665 | 9,533 dtc + 132 pid | 0 | 25 (`V002`) | 34.5 s |
| wal33d | 18,805 | 18,805 dtc | 0 | 64 (`V020` 59, `V004` 5) | 3.3 s |
| autodiag | 30,075 | 28,832 dtc + 1,085 ecu + 157 vehicle | **1** (`P15O9`, `V001`) | 4 (`V004`) | 33.5 s |
| obdb | 590 | 8 vehicle + 2 ecu + 580 pid | 0 | 0 | 0.1 s |

**Totals:** 59,135 raw records → 57,170 DTC records staged, 1 quarantined, 59,134 immutable
`source_records`, 30,087 `source_files`, 804,308 validation results (93 failed: all warnings, plus the
one blocking error behind the quarantine).

## 5. Unique codes and identities

| Metric | Value |
| --- | ---: |
| DTC records staged | 57,170 |
| **Distinct codes** | **19,216** |
| **DTC identities (code + standard + context)** | **40,222** |
| — generic | 12,947 |
| — manufacturer | 26,409 |
| — ECU | 866 |
| — vehicle-variant | 0 (no source documents such a link) |
| Definitions | 65,108 (55,575 en, 9,533 de, 0 ar) |
| Verified / source-reported / conflicting | 14,029 / 42,108 / 8,971 |
| Manufacturers · ECUs · vehicles · variants | 41 · 1,088 · 166 · 9 |
| Causes · symptoms · repairs · related codes · components | 28,334 · 26,283 · 9,533 · 32,361 · 23,176 |
| PIDs | 712 |

`P1690` is stored **22 times** (one per manufacturer that documents it) — the proof that `code` is
not a unique key. `P0420` keeps the generic statement and, separately, the Audi-specific one.

## 6. Duplicates

| Kind | Groups | What happened |
| --- | ---: | --- |
| `exact_statement` | 8,573 | merged into one definition row with several provenance claims (6,482 pairs, 2,091 triples) |
| `near_statement` | 1,465 | reported only — **both rows kept**, no merging by similarity |
| `code_context_variants` | 4,186 | reported as *not* duplicates (same code, different context) |
| **Total groups** | **14,224** | stored in `duplicate_groups` / `duplicate_members` |

Identical statements from the same source are counted as `same_source_variants`, not as
corroboration and not as duplicates.

## 7. Conflicts needing review

| Metric | Value |
| --- | ---: |
| Open conflicts (`status = needs_review`) | **4,435** |
| Type | `definition_disagreement` (4,435) |
| Definitions flagged `conflicting` | 8,971 |
| Conflicts by cause/flag disagreement | 0 (no source supplies comparable cause or flag data for the same identity) |

Each conflict stores both statements, their sources and the claims behind them. Nothing was
resolved by majority vote, and no statement was deleted.

## 8. Test results

```
$ pytest -q                     # 173 passed, 4 skipped
$ AUTODOCTOR_INTEGRATION=1 pytest -m integration -q
4 passed                        # against the real checkouts
$ ruff check src tests
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
| database (build 17, queries 9, provenance 6, translations 6, app bundle 3) | 41 |
| CLI | 14 |
| change detection | 3 |
| models | 6 |
| real sources (opt-in) | 4 |
| **Total** | **177** |

## 9. Problems found (and what was done about them)

1. **`dtc_tests` is empty (0 rows).** No upstream provides verification procedures; the autodiag2
   fields that would hold them are absent from every real record. Table, texts, provenance and
   validators are implemented and tested — content is a phase-2 authoring task.
2. **No Arabic (0 rows).** No source contains Arabic. The engine refuses machine translation and
   accepts only reviewed human translations; a CSV template generator and the loader are ready.
3. **autodiag2 payload is much thinner than its schema suggests.** Only code, definition, created,
   updated, protocol, standard and evidence are ever populated. The connector takes exactly those —
   it does not invent causes or repairs.
4. **autodiag2 and OBDb are share-alike and unreviewed.** `D007` is the only failing gate. Public
   distribution is blocked until the licence review closes (plan: public bundle = OBDex + Wal33D).
5. **Wal33D's compiled SQLite does not match its shipped text lists** (18,805 rows vs 18,826
   parseable lines). Recorded as an inspection warning; the richer compiled database is imported.
6. **`evidence` is not independence.** 27,967 autodiag2 files cite `obdcodex`; corroboration counts
   lineages, so autodiag2 alone cannot verify anything.
7. **Two data smells that are real, not bugs:** `dtc_repairs` (9,533) exactly equals the OBDex code
   count because only OBDex has repair data; `manufacturers` includes an `Unspecified` bucket
   (2,620 identities) from Wal33D's `OTHER` label — kept and documented rather than discarded.
8. **One invalid upstream code** (`P15O9`, letter O) is quarantined, not silently repaired.
9. **The app bundle is 60 MB** (147 MB before dropping the claim matrix). Acceptable for a first
   run, worth a "lite" variant.
10. **`P1690`-style ambiguity is the norm:** 198 codes in Wal33D are both generic and
    manufacturer-specific. The UI must always show which context is displayed.

## 10. Next step

Phase 2, in this order (see [DEVELOPMENT_PLAN](DEVELOPMENT_PLAN.md)):

1. Close the licence review for autodiag2/OBDb; add `--source-set public|private`; make `D007`
   blocking for public bundles.
2. Start the Arabic programme on the generic layer using `export-translation-template`.
3. Author `dtc_tests` content for the highest-risk generic codes.
4. Build the conflict review workflow (4,435 decisions) and make decisions survive rebuilds.
5. Add the scheduled upstream-drift run to a real branch and open issues from it.

---

## Structure and plan — for approval

**Repository structure** (what is committed; generated data stays out of git):

```
config/   db/schema.sql   docs/   src/autodoctor_data_engine/   tests/   data/translations/
.github/workflows/   README.md   THIRD_PARTY_NOTICES.md   LICENSE   pyproject.toml
```

**Merge pipeline** that produced 0.1.0 — to be confirmed before it is treated as final:

1. import per source → immutable raw archive + normalized staging + validation log;
2. validate → blocking failures quarantine the record, warnings are stored;
3. dedupe → exact merges, near/context reported only;
4. conflicts → cross-lineage disagreement stored with evidence, nothing deleted;
5. merge → deterministic canonical choice, lineage-based verification, derived risk rule;
6. gates → FK, provenance, uniqueness, canonical, related, licence, claim sources, emptiness, numeric;
7. publish → SQLite + app bundle + manifest (SHA-256) + `db_versions` row.

**Decisions requested**

| # | Decision | Recommendation |
| --- | --- | --- |
| 1 | Approve this repository structure | approve as-is |
| 2 | Approve the merge/identity rules above | approve; `P1690`-style multi-meaning codes stay separate |
| 3 | Make the GitHub repository public? | **not yet** — the code can be public, but no exported database until the two licence reviews close |
| 4 | Public bundle source set | OBDex (CC0) + Wal33D (MIT) only, plus local translations |
| 5 | Arabic source | human translation batches, reviewed; no machine translation |
| 6 | `dtc_tests` content | author in phase 2, one reviewed batch per system |
