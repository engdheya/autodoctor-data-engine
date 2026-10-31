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
published release (`0.1.0`), with 177 automated tests.

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

> **مبدأ أساسي:** كود العطل يشير إلى *منطقة عطل* وليس إلى قطعة تالفة. لهذا تحمل كل معلومة حالة
> تحقق (`verified` / `source_reported` / `conflicting` / `unverified`) وتُعرض التعارضات بدل إخفائها.

---

## What this engine produces (release 0.1.0, measured)

| Metric | Value |
| --- | ---: |
| DTC identities (code + context) | 40,222 |
| Distinct DTC codes | 19,216 |
| Definitions (EN + DE) | 65,108 |
| Verified definitions (≥2 independent lineages) | 14,029 |
| Definitions flagged as conflicting | 8,971 |
| Causes / symptoms / repairs / related codes | 28,334 / 26,283 / 9,533 / 32,361 |
| PIDs and vehicle parameters | 712 |
| Provenance claims | 327,369 |
| Open conflicts for review | 4,435 |
| Duplicate groups (exact / near / context-variants) | 8,573 / 1,465 / 4,186 |
| Arabic definitions | 0 (no source provides Arabic; see below) |

Every number above is queried from the built database, never estimated. Reproduce with
`autodoctor report`.

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
autodoctor fetch-sources --all        # OBDb clones a handful of vehicle repositories

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

# 6. merge, gate and publish
autodoctor build-db --version 0.1.0

# 7. ask questions of the result
autodoctor report
autodoctor search P0301
autodoctor explain P0301
autodoctor version
```

`autodoctor run-all` performs steps 4 and 6 in one go.

## CLI reference

| Command | Purpose |
| --- | --- |
| `inspect-sources [--source S]` | layout, commit, licence and warnings per source; writes `data/reports/source-inspection.{json,md}` |
| `fetch-sources [--source S] [--limit N]` | shallow-clone missing checkouts into `vendor/upstream` |
| `import --source S \| --all [--fail-on-error] [--limit N]` | raw archive + normalized staging + validation log |
| `validate [--source S]` | aggregate validation results of the staged imports (exit 1 on blocking failures) |
| `detect-duplicates [--source S] [--limit N]` | exact / near duplicates and code-in-many-contexts |
| `detect-conflicts [--source S] [--limit N]` | statements that contradict each other |
| `build-db [--version X] [--part major\|minor\|patch] [--strict] [--no-export] [--no-app-bundle]` | merge, run release gates, publish |
| `report [--imports] [--write]` | database or import report (markdown + JSON) |
| `search CODE [--json]` | the diagnostic card the Flutter app will show |
| `explain CODE [--context K] [--lang L] [--json]` | full provenance: source, commit, file, record, licence, status, conflicts |
| `detect-changes [--previous F] [--current F]` | diff two builds: moved sources, new/changed/vanished records, added/removed codes |
| `export-translation-template [--lang ar] [--limit N]` | CSV of codes still missing a translation |
| `version` | engine version + published release manifest |
| `run-all` | import every enabled source, then build |

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
  AR: -                       # no reviewed Arabic translation yet
  causes: 3  symptoms: 2  tests: 0  repairs: 1  sources: 3
  risk: high
```

`autodoctor explain P0301` then shows that this statement comes from OBDex (CC0-1.0,
commit `a9d0220…`, `data/generic/P0xxx_enriched.yaml`) and is corroborated by Wal33D and
autodiag2, while `P1690` is deliberately *two* different codes (Ford "Wastegate Solenoid
Circuit Malfunction" vs BMW "Malfunction Indicator Lamp MIL Electrical").

## Repository layout

```
config/sources.yaml          source registry: paths, licences, lineages, import scope, rules
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
  versioning/                semver + release manifest
  database/                  schema loading, repository, build orchestration, app bundle
  reporting/                 import / quality / change reports
  pipeline.py, cli.py        orchestrator and command line
data/  raw/ staging/ processed/ exports/ translations/ reports/   (generated, git-ignored)
tests/                                                                177 tests
docs/                                                                 see below
```

## Design decisions that matter

1. **`code` is not a unique key.** Identity is `(code, standard, context)` where context is
   `generic`, `manufacturer`, `ecu` or `vehicle_variant`. P1690 has 22 different meanings across
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
7. **Two artifacts.** A 147 MB engineering database (full provenance, validation, duplicate
   evidence) and a 60 MB app bundle (content + compact provenance) for the phone.

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

## Data licensing (short version)

The engine code is MIT. The merged database is **not** MIT: it contains data under several
licences.

* OBDex data — CC0-1.0 (public domain, no obligations)
* Wal33D data — MIT (keep the copyright notice)
* autodiag2 data — ODbL-1.0 / DbCL-1.0, **share-alike**, marked *pending review*
* OBDb data — CC-BY-SA-4.0, **share-alike**, marked *pending review*

Release gate `D007` fails public distribution while any share-alike source is unreviewed. Read
[LICENSES](docs/LICENSES.md) before publishing a bundle outside your own devices.

## Contributing

* `pytest` must stay green; `pytest -m integration` additionally exercises the real checkouts.
* Never edit `data/raw/**`: it is the audit trail.
* A new source means: a registry entry with a licence record, a connector under
  `connectors/`, fixture checkouts under `tests/fixtures/`, and tests for its real layout.
* Do not add a fact dimension the upstream does not provide. Empty columns are honest;
  invented content is not.
