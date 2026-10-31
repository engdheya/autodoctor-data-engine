# Architecture

```
                     ┌──────────────────────────────────────────────┐
                     │            config/sources.yaml               │
                     │  paths · licences · lineages · scope · rules │
                     └───────────────────┬──────────────────────────┘
                                         │
   ┌──────────────┐   RawRecord   ┌──────▼───────┐  NormalizedRecord  ┌────────────┐
   │  connectors  │──────────────►│  pipeline    │───────────────────►│ validators │
   │  4 sources   │   verbatim    │  extract     │   shared models    │ rule engine│
   └──────────────┘               │  + archive   │                    └─────┬──────┘
                                  └──────┬───────┘                          │
                                         │ data/raw/<slug>/<commit>/*.jsonl │ issues
                                         │ data/staging/<slug>/<commit>/    │
                                         ▼                                  ▼
                                  ┌──────────────┐                  ┌──────────────┐
                                  │  staging     │                  │ validation   │
                                  │ JSONL + hash │                  │ JSONL + agg  │
                                  └──────┬───────┘                  └──────────────┘
                                         │
                        ┌────────────────┴─────────────────┐
                        ▼                                  ▼
                ┌───────────────┐                  ┌────────────────┐
                │ deduplication │                  │  conflicts     │
                │ exact/near/   │                  │  cross-source  │
                │ context       │                  │  disagreements │
                └───────┬───────┘                  └───────┬────────┘
                        └──────────────┬───────────────────┘
                                       ▼
                              ┌─────────────────┐
                              │  merge loader   │  identity · canonical · verification
                              └────────┬────────┘
                                       ▼
                       ┌───────────────────────────────┐
                       │ SQLite  db/autodoctor.sqlite  │
                       └───────────────┬───────────────┘
                                       │ release gates (FK, provenance, uniqueness, licences)
                                       ▼
                 ┌──────────────────────┐   ┌────────────────────────┐
                 │ data/exports/…sqlite │   │ autodoctor-app-…sqlite │
                 │ engineering artifact │   │ Flutter bundle         │
                 └──────────────────────┘   └────────────────────────┘
```

## Layers and their contracts

### 1. Configuration (`config.py`, `config/sources.yaml`)

Every source is declared with a path, a licence record (code licence and *data* licence
separately), a lineage group, an import scope, and a legal review status. Nothing enters the
pipeline that is not declared here. `paths` and `local_path` support `${ENV:-default}` expansion
so the same registry works locally and in CI.

### 2. Connectors (`connectors/`)

A connector has exactly two jobs:

* `extract()` — yield `RawRecord(record_type, source_record_id, file_path, payload)` verbatim from
  the upstream checkout. No cleaning.
* `normalize(raw, provenance_base)` — map one raw record to zero or more `NormalizedRecord`s using
  the shared normalizers.

Everything else (hashing, archiving, validation, dedup, merge) belongs to the pipeline, so a new
source cannot bypass provenance. `version_info()` is separate from `inspect()`: importing needs
only the commit/label, while `inspect()` parses the whole tree (28 833 YAML files for autodiag2)
and is only used by `inspect-sources`.

### 3. Parsers (`parsers/`)

Format readers return plain Python objects and never mutate input: YAML (with multi-document
support), JSON, read-only SQLite, CSV/TSV with dialect sniffing, and the `CODE - description`
text lists that Wal33D ships. Errors always name the offending file.

### 4. Normalizers (`normalizers/`)

Pure functions, fully unit-tested:

* codes: uppercase, strip scan-tool noise (`DTC P0-301`, zero-width characters), and *classify*
  (category, standard) without ever rewriting an identity. `P15O9` (letter O) stays invalid
  instead of being "repaired" into `P1509`.
* text: Unicode NFC, whitespace collapse, empty→NULL.
* languages: `EN-us`, `de_DE`, `ara` → `en`, `de`, `ar`.
* manufacturers: alias table (`CHEVY`→Chevrolet, `MERCEDES`→Mercedes-Benz, `VW`→Volkswagen) plus
  non-manufacturer labels (`GENERIC`, `OTHER`, `saej2012.2002`) that must never become entities.
* keys: stable ASCII snake_case keys for causes/symptoms/components so the same concept from two
  sources can be compared.

### 5. Intermediate models (`models.py`)

Pydantic models are the contract between layers. `Context` refuses to exist without its target
(a manufacturer context without a manufacturer is a bug, not a warning), and `context_key` is
derived in exactly one place.

### 6. Pipeline (`pipeline.py`)

`import_source()` streams three artifacts to disk:

| Artifact | Path | Purpose |
| --- | --- | --- |
| raw archive | `data/raw/<slug>/<commit>/<type>.jsonl` | verbatim upstream payloads + hash; never rewritten |
| staging | `data/staging/<slug>/<commit>/normalized.jsonl` | normalized records (the merge input) |
| validation log | `data/staging/<slug>/<commit>/validation.jsonl` | every rule result, passed or failed |
| manifest | `data/staging/<slug>/<commit>/manifest.json` | commit, file hashes, counts, content hash |

Records that fail a blocking rule are quarantined: they are logged and counted, never staged.
`--fail-on-error` turns any quarantine into an import failure. Streaming keeps memory flat
(57 170 DTC records peak well under 200 MB).

### 7. Validation (`validators/`)

Record rules (`V001`…`V020`) and database gates (`D001`…`D010`) are separate. Blocking rules are
listed in `BLOCKING_RULES`; the release gate reads the built file, not the in-memory state.

### 8. Deduplication and conflict resolution

Both operate on the *same* normalized records and both compare headlines (title, falling back to
description) rather than concatenated prose — otherwise "title + paragraph" vs "title" would look
like disagreement.

* exact: same canonical headline in the same `(code, context, language)` → one definition row,
  several claims.
* near: similarity ≥ threshold but < 1 → group reported, rows kept separate.
* context variants: same code in several contexts → reported as *not* duplicates.
* conflicts: statements from different lineages that do not agree → one conflict row per
  `(code, context, language)` with every competing statement as evidence.

### 9. Merge (`merger/`)

`MergeLoader` inserts content and, for every fact, a `provenance_claims` row pointing at a
`source_records` row. Then three post-passes run:

1. **canonical selection** — per `(code, language)`, deterministic: source precedence
   (OBDex → Wal33D → autodiag2 → OBDb), then the richest text.
2. **verification** — `verified` when ≥ *N* distinct lineages state the same thing (byte-equal, or
   same headline); `conflicting` when the conflict pass marked the row; otherwise
   `source_reported`.
3. **derived risk** — a documented rule (`risk_flags_v1`) over MIL/emissions/limp-mode flags,
   stored with its basis JSON and its own derived claim.

### 10. Publication (`database/build.py`, `versioning/`)

The build always produces the working database, then evaluates gates. If a blocking gate fails or
(`--strict`) any record is quarantined, the export and manifest are not produced; a
`data/reports/failed-build-<version>.json` explains why. On success it writes:

* `data/exports/autodoctor-<version>.sqlite` — engineering artifact
* `data/exports/autodoctor-app-<version>.sqlite` — Flutter bundle
* `data/exports/autodoctor-<version>.manifest.json` — commits, licences, counts, checks, SHA-256
* a `db_versions` row inside the database itself

## Invariants

1. **No fact without provenance.** Enforced by construction and by gate `D003`.
2. **Raw is immutable.** `data/raw/**` is written once per commit; normalization never touches it.
3. **Identity is contextual.** `context_key` is unique; `code` is not.
4. **No silent resolution.** Conflicts and near duplicates are stored, never resolved by vote.
5. **Deterministic output.** Same commits + same code ⇒ same content hash, same canonical choices,
   same manifest counts (translation timestamps aside).
6. **Fail closed.** Publishing requires gates; strict mode requires zero quarantined records.

## Failure modes and how they surface

| Failure | Behaviour |
| --- | --- |
| checkout missing | `inspect-sources` reports `present: false`; `import` raises `ConnectorError` with the fetch command |
| malformed YAML/JSON | parser raises with the file name; the import aborts for that source only |
| one bad record | quarantined with rule id and message; counted in the manifest and in `validate` |
| upstream schema drift | the field simply normalizes to NULL and the record surfaces as `V003`/`V004` warnings |
| licence not approved | `D007` warning today, blocks the public bundle once `blocked_redistribution_review` is enforced |
| gate failure | no export; `failed-build-<version>.json` lists the offending check |

## Extension points

* **New source** — registry entry + connector + fixtures + tests. Nothing else changes.
* **New content dimension** — add the table, a claim per fact, and a validator rule.
* **Better Arabic coverage** — drop reviewed YAML into `data/translations/ar/` and rebuild; the
  pipeline attaches it as `is_translated` with translator/reviewer provenance.
* **New risk rule** — add `risk_<name>_v1` in the loader; the rule id is stored with every value so
  historical rows keep their meaning.
