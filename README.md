# AutoDoctor Data Integration Engine

The data engine behind **AutoDoctor AI**. It reads automotive diagnostic trouble code (DTC)
databases from several upstream projects, preserves the raw records, normalizes and validates
them, detects duplicates and contradictions, and merges the accepted facts into one traceable
SQLite database that a Flutter app can ship and search offline.

```
GitHub sources ──► extract ──► raw archive ──► normalize ──► validate ──► dedupe/conflicts
                                                                                    │
                          Flutter app  ◄── app bundle ◄── publish ◄── merge ◄───────┘
```

**Status:** Phase 1 complete and working end to end. Four real sources are integrated into a
published engine release (`0.1.0`) building database version `0.4.0` in two separately licensed
editions — a **private** database with all four sources and a **public** one restricted to the
licences that are cleared for redistribution. 210 automated tests (205 pass; the 5 real-upstream
integration tests are opt-in).

---

## نبذة بالعربية

هذا المستودع هو **محرك البيانات** لمشروع AutoDoctor AI، وليس تطبيق Flutter. وظيفته:

1. قراءة أربعة مصادر حقيقية لأكواد أعطال السيارات (OBDex، Wal33D، autodiag2، OBDb).
2. حفظ السجلات الأصلية كما هي قبل أي تعديل (أرشيف JSONL نهائي لا يُعدّل).
3. توحيد الأكواد والأسماء واللغات، والتحقق من صحة كل سجل بقواعد صريحة.
4. اكتشاف التكرار الحقيقي، وفصل الأكواد المتشابهة التي تعني أشياء مختلفة في سياقات مختلفة.
5. تسجيل التعارضات بين المصادر دون حذف أي رأي ودون اختيار الأكثر تكرارًا.
6. الاحتفاظ بسلسلة مصدر كاملة لكل معلومة: المستودع، الـ commit، الملف، السجل، الترخيص، وتاريخ الاستيراد.
7. بناء قاعدة SQLite موحّدة + نسخة أصغر مخصّصة لتطبيق Flutter.
8. إصدار نسخة مرقّمة مع Manifest و SHA-256، ولا تُنشر أي نسخة إذا فشلت بوابات الجودة.
9. **فصل حقيقي بين قاعدة عامة وأخرى خاصة**: نسخة `private` تضم المصادر الأربعة، ونسخة `public`
   لا تدخلها بيانات autodiag2 وOBDb قبل اكتمال المراجعة القانونية — والمنع مفروض في الكود
   (بوابة `D011` + `--source-set public`) ومغطّى باختبارات، لا مجرّد توثيق.
10. **أداة مراجعة التعارضات**: لكل تعارض بصمة ثابتة، وقرار المراجع يُحفظ في
    `data/reviews/conflicts.yaml` فلا يُعاد طرح التعارض المحلول في البناء التالي.

> **مبدأ أساسي:** كود العطل يشير إلى *منطقة عطل* وليس إلى قطعة تالفة. لهذا تحمل كل معلومة حالة
> تحقق (`verified` / `source_reported` / `conflicting` / `unverified`) وتُعرض التعارضات بدل إخفائها.

---

## What this engine produces (database 0.4.0, measured 2026-11-01)

The two editions are built from the same code with `--source-set public|private`. Every number is
queried from the built database, never estimated; reproduce with `autodoctor report`.

| Metric | Private (4 sources) | Public (2 sources) |
| --- | ---: | ---: |
| DTC identities (code + context) | 40,222 | 19,089 |
| Distinct DTC codes | 19,216 | 12,412 |
| Definitions (EN + DE) | 65,108 | 37,871 |
| Verified definitions (≥2 independent lineages) | 14,029 | 16,652 |
| Definitions flagged as conflicting | 8,971 | 1,006 |
| Causes / symptoms / repairs / related codes | 28,334 / 26,283 / 9,533 / 32,361 | identical (OBDex + Wal33D only) |
| Components | 23,176 | 23,176 |
| PIDs and vehicle parameters | 1,541 | 132 |
| Vehicles / ECUs / manufacturers | 1,538 / 1,105 / 163 | 0 / 0 / 33 |
| Evidence citations | 61,729 | 32,944 |
| Provenance claims | 352,761 | 233,432 |
| Open conflicts for review | 4,435 | 503 |
| Duplicate groups (exact / near / context-variants) | 8,573 / 1,465 / 4,186 | 8,326 / 321 / 940 |
| Validation records (warnings / errors) | 808,740 (93 / 0) | 396,996 (89 / 0) |
| Release gates | 9 / 11 (D007, D011 warn: two sources pending review) | 11 / 11 |
| Size (database / app bundle) | 169.5 MB / 71.2 MB | 105.8 MB / 52.1 MB |
| Arabic definitions | 0 (no source provides Arabic; see below) | 0 |

The public edition has *more* verified definitions than the private one because verification counts
independent lineages, and the two share-alike sources mostly re-report OBDex (see
[design decision 5](#design-decisions-that-matter)).

**Arabic:** none of the four upstream databases provides Arabic. The engine therefore does not
invent translations: it accepts reviewed human translations from `data/translations/ar/*.yaml`,
loads them with translator/reviewer provenance, and ships a CSV template
(`autodoctor export-translation-template`) for the translation work. See
[DATA_DICTIONARY](docs/DATA_DICTIONARY.md#languages).

---

## Quick start

```bash
# 1. install (Python 3.11+)
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. clone the upstream sources into vendor/upstream (or point AUTODOCTOR_UPSTREAM_DIR elsewhere)
autodoctor fetch-sources              # OBDb clones a handful of vehicle repositories (--limit N)

# 3. see what was found (commits, licences, layouts, problems)
autodoctor inspect-sources

# 4. extract + archive + normalize + validate, per source
autodoctor import --source obdex
autodoctor import --source wal33d
autodoctor import --source autodiag
autodoctor import --source obdb

# 5. inspect the data quality decisions before merging
autodoctor validate
autodoctor detect-duplicates
autodoctor detect-conflicts

# 6. see which sources each edition may contain
autodoctor source-set            # public: obdex + wal33d; excluded: autodiag, obdb (review pending)

# 7. merge, gate and publish
autodoctor build-db --version 0.4.0 --source-set private   # all four sources, internal use
autodoctor build-db --version 0.4.0 --source-set public    # only licence-cleared sources

# 8. ask questions of the result
autodoctor report
autodoctor search P0301
autodoctor explain P0301
autodoctor version
```

`autodoctor run-all --source-set public` performs steps 4 and 7 in one go. `build-db` **fails closed**:
a public build that contains a fact from an unapproved source is refused by gate `D011`.

## CLI reference

| Command | Purpose |
| --- | --- |
| `inspect-sources [--source S]` | layout, commit, licence and warnings per source; writes `data/reports/source-inspection.{json,md}` |
| `fetch-sources [--source S] [--limit N]` | shallow-clone missing checkouts into `vendor/upstream` |
| `import --source S \| --all [--fail-on-error] [--limit N]` | raw archive + normalized staging + validation log |
| `validate [--source S]` | aggregate validation results of the staged imports (exit 1 on blocking failures) |
| `detect-duplicates [--source S] [--limit N]` | exact / near duplicates and code-in-many-contexts |
| `detect-conflicts [--source S] [--limit N]` | statements that contradict each other |
| `build-db [--version X] [--part major\|minor\|patch] [--source-set public\|private] [--source S] [--strict] [--no-export] [--no-app-bundle]` | merge, run release gates, publish one edition |
| `report [--imports] [--write]` | database or import report (markdown + JSON) |
| `coverage [--database F] [--write] [--json]` | measured coverage per declared field, with denominators, plus the declared scope and its gaps |
| `search CODE [--json]` | the diagnostic card the Flutter app will show |
| `explain CODE [--context K] [--lang L] [--json]` | full provenance: source, commit, file, record, licence, status, conflicts |
| `detect-changes [--previous F] [--current F]` | diff two builds: moved sources, new/changed/vanished records, added/removed codes |
| `export-translation-template [--lang ar] [--limit N]` | CSV of codes still missing a translation |
| `source-set` | which sources each edition may use, and why the others are excluded |
| `list-conflicts [--code C] [--status needs_review\|resolved\|accepted_difference\|all] [--limit N]` | review queue with stable conflict fingerprints |
| `review-conflict FINGERPRINT (--accept \| --resolve --source S) --note … --reviewer …` | record a human decision, persisted in `data/reviews/conflicts.yaml` |
| `version` | engine version + published release manifest |
| `run-all [--source-set public\|private] [--source S]` | import every source of the set, then build |

Global flags: `--root` (project directory), `--json` (machine readable).

## How a DTC is looked up

```sql
-- the app's primary lookup: one row per (code, context), best language available
SELECT * FROM v_dtc_summary
WHERE code = 'P0301'
ORDER BY context_type, manufacturer;
```

```console
$ autodoctor search P0301
P0301  [generic]
  EN: Cylinder 1 Misfire Detected
  causes: 5  symptoms: 4  tests: 0  repairs: 1  sources: 2
  risk: high

P0301  [manufacturer: Audi]
  EN: Worn out spark plugs, ignition wires, coil(s), distributor cap and rotor (when applicable), …
  causes: 0  symptoms: 0  tests: 0  repairs: 0  sources: 1

Reminder: a DTC identifies a fault *area*, not a failed part. Always confirm with the listed tests.
```

The full walkthrough — every table, every citation, verbatim output — is in
[EXAMPLE_P0301](docs/EXAMPLE_P0301.md).

`autodoctor explain P0301` then shows that this statement comes from OBDex (CC0-1.0,
commit `a9d0220…`, `data/generic/P0xxx_enriched.yaml`), is corroborated by Wal33D (MIT), carries 7
upstream citations and no conflict, while `P1690` is deliberately *34* different manufacturer meanings — e.g. Ford
"Wastegate Solenoid Circuit Malfunction" vs BMW "Malfunction Indicator Lamp MIL Electrical".
In the public edition autodiag2 is absent, so the audi manufacturer context — which comes from
Wal33D — is the only manufacturer row for P0301.

## Repository layout

```
config/sources.yaml          source registry: paths, licences, lineages, import scope, rules
ci/                          GitHub Actions definitions (activate with `cp ci/*.yml .github/workflows/`)
db/schema.sql                the canonical SQLite schema (context-aware, provenance-first)
src/autodoctor_data_engine/
  connectors/                one connector per upstream project (extract + normalize only)
  parsers/                   yaml / json / sqlite / csv / plain-text readers
  normalizers/               codes, text, languages, manufacturer aliases, stable keys
  validators/                record rules, database gates, blocking-rule registry
  deduplication/             exact vs near vs context-variant detection
  conflict_resolution/       cross-source disagreement, one conflict per statement
  merger/                    merge loader (identity, canonical choice, verification)
  provenance/                "where does this come from" queries
  pipeline.py, staging.py    orchestrator, staging manifests and bundles
  versioning/                semver + release manifest
  database/                  schema loading, repository, build orchestration, app bundle
  reporting/                 import / quality / change reports
  pipeline.py, cli.py        orchestrator and command line
data/  raw/ staging/ processed/ exports/ translations/ reports/   (generated, git-ignored)
tests/                                                                210 tests
docs/                                                                 see below
```

## Design decisions that matter

1. **`code` is not a unique key.** Identity is `(code, standard, context)` where context is
   `generic`, `manufacturer`, `ecu` or `vehicle_variant`. P1690 has 34 different meanings across
   the Wal33D manufacturer tables; the database keeps all of them.
2. **Nothing is merged by similarity.** Exact duplicates collapse into one row with several
   provenance claims. Near duplicates are reported and both rows survive. Different contexts are
   never compared.
3. **Conflicts keep both sides.** No majority vote, no silent overwrite. Both statements stay,
   both are marked `conflicting`, and the evidence is stored for review.
4. **Provenance is structural, not documentation.** A fact cannot be inserted without a claim
   pointing at an immutable source record; release gate `D003` verifies it.
5. **Corroboration counts lineages, not repositories.** autodiag2 reports `obdcodex` as its
   evidence for ~97 % of its records, so it shares a lineage with that upstream and does not by
   itself turn a statement into "verified".
6. **Fail closed.** A release is only published when the database gates pass; `--strict` also
   refuses to publish while any record is quarantined.
7. **Two editions, two artifacts each.** A *private* database (169.5 MB, all four sources, full
   provenance, validation and duplicate evidence) and a *public* one (105.8 MB, licence-cleared
   sources only), each with a smaller app bundle (71.2 MB / 52.1 MB: content + compact provenance)
   for the phone. See [PUBLICATION](docs/PUBLICATION.md).

## Documentation

| Document | Contents |
| --- | --- |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | layers, data flow, guarantees, failure modes |
| [DATABASE_SCHEMA](docs/DATABASE_SCHEMA.md) | every table and column, why it exists |
| [DATA_SOURCES](docs/DATA_SOURCES.md) | what each upstream actually contains, measured |
| [LICENSES](docs/LICENSES.md) | code vs data licences, obligations, review status |
| [DATA_DICTIONARY](docs/DATA_DICTIONARY.md) | enumerations, verification statuses, risk rule, languages |
| [DEVELOPMENT_PLAN](docs/DEVELOPMENT_PLAN.md) | phases, what is done, what comes next |
| [FLUTTER_INTEGRATION](docs/FLUTTER_INTEGRATION.md) | bundle layout, queries, update strategy |
| [PHASE1_REPORT](docs/PHASE1_REPORT.md) | the delivery report for phase 1 |
| [PUBLICATION](docs/PUBLICATION.md) | public vs private editions, the four licence controls, measured comparison |
| [EXAMPLE_P0301](docs/EXAMPLE_P0301.md) | end-to-end walkthrough: import → build → search → explain for P0301 |
| [CONFLICT_REVIEW](docs/CONFLICT_REVIEW.md) | fingerprints, `list-conflicts` / `review-conflict`, how decisions survive a rebuild |
| [INTEGRATION_RESULTS](docs/INTEGRATION_RESULTS.md) | the four connectors run against the real upstream repositories |
| [PHASE2_TRANSLATION_PLAN](docs/PHASE2_TRANSLATION_PLAN.md) | reviewed human Arabic: glossary, batches, gates |
| [PHASE2_DTC_PROCEDURES_PLAN](docs/PHASE2_DTC_PROCEDURES_PLAN.md) | inspection procedures: schema, authoring, review, UI rules |
| [FINAL_PLAN](docs/FINAL_PLAN.md) | phases A–J for the production dataset, and what is blocked by what |
| [LICENSE_COMPLIANCE_REPORT](docs/LICENSE_COMPLIANCE_REPORT.md) | per-source licences, obligations, and proof of what the public artifact contains |
| [DATA_COVERAGE_REPORT](docs/DATA_COVERAGE_REPORT.md) | measured coverage with explicit denominators, generated from the artifact |

## Data licensing (short version)

The engine code is MIT. The merged database is **not** MIT: it contains data under several
licences.

* OBDex data — CC0-1.0 (public domain, no obligations)
* Wal33D data — MIT (keep the copyright notice)
* autodiag2 data — ODbL-1.0 / DbCL-1.0, **share-alike**, marked *pending review*
* OBDb data — CC-BY-SA-4.0, **share-alike**, marked *pending review*

Gate `D007` reports unreviewed share-alike sources and gate `D011` **refuses** to build a public
database that contains any of their facts — the restriction is enforced by
`--source-set public` and checked by an assertion inside `build_app_bundle`, not just documented.
See [PUBLICATION](docs/PUBLICATION.md) and [LICENSES](docs/LICENSES.md) before publishing a bundle
outside your own devices.

## Contributing

* `pytest` must stay green (210 tests); `AUTODOCTOR_INTEGRATION=1 pytest tests/test_integration_real_sources.py`
  additionally exercises the real checkouts.
* Never edit `data/raw/**`: it is the audit trail.
* A new source means: a registry entry with a licence record, a connector under
  `connectors/`, fixture checkouts under `tests/fixtures/`, and tests for its real layout.
* Do not add a fact dimension the upstream does not provide. Empty columns are honest;
  invented content is not.
