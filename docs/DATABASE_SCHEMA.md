# Database schema

SQLite, versioned by `schema_version` (currently `1`). The canonical DDL is
[`db/schema.sql`](../db/schema.sql); every build re-creates the file from it, so the schema is
never patched by hand.

```
data_sources ─┬─ data_versions ─┬─ source_files ── source_records ─┐
              └─────────────────┴─ provenance_claims ◄─────────────┘
manufacturers ─┬─ vehicles ── vehicle_variants ── vehicle_ecu_links ── ecus
               └────────────────────────────┐
                                             ▼
dtc_codes ─┬─ dtc_definitions (1..n, per language)
           ├─ dtc_causes ── dtc_cause_texts
           ├─ dtc_symptoms ── dtc_symptom_texts
           ├─ dtc_tests ── dtc_test_texts
           ├─ dtc_repairs ── dtc_repair_texts
           ├─ dtc_related_codes
           ├─ dtc_components ── dtc_component_texts
           ├─ dtc_flags
           ├─ translations
           └─ conflicts ── conflict_evidence
pids ── pid_texts
validation_results · duplicate_groups ── duplicate_members · db_versions
```

---

## 1. Source registry

### `data_sources`
One row per upstream project. Licences are split into `code_license` (the repository's source
code) and `data_license` / `contents_license` (what we actually redistribute).

| Column | Meaning |
| --- | --- |
| `slug` | stable identifier used everywhere (`obdex`, `wal33d`, `autodiag`, `obdb`, `local-translations`) |
| `code_license`, `data_license`, `contents_license`, `data_license_url` | the licence facts, from the repository, not from memory |
| `attribution_required`, `share_alike`, `redistribution_allowed`, `commercial_use_allowed` | machine-checkable obligations (gate `D007`) |
| `legal_review_status` | `pending` / `approved` / `rejected`; drives whether a public bundle may ship |
| `lineage_group` | the *actual* origin of the data. autodiag2 → `obdcodex`, because its evidence field says so |

### `data_versions`
One row per imported upstream commit: `commit_sha`, `retrieved_at`, `file_count`, `record_count`,
`content_hash` (hash over all file hashes). `UNIQUE(source_id, commit_sha)` makes re-importing the
same commit idempotent. OBDb is a multi-repository source, so it stores a synthetic version label
`obdb:<hash>` and keeps the per-repository commits in the inspection report.

### `source_files`
Every parsed file with its SHA-256, byte size and record count. This is what makes a build
reproducible and lets a reviewer diff an upstream release.

### `source_records`
The immutable upstream record: `source_record_id` (as the connector names it, e.g.
`data/generic/P0xxx_enriched.yaml#P0301`), `record_type`, `raw_hash`, `raw_archive_path` (the JSONL
line that holds the verbatim payload) and optional `raw_json`. Omitting `raw_json` keeps the
distribution database small; the archive is the authoritative copy.

## 2. Vehicles, ECUs, parameters

| Table | Content |
| --- | --- |
| `manufacturers` | canonical names (`Chevrolet`, not `CHEVY`), slug, optional country |
| `vehicles` | manufacturer + model + generation + year range + description (from OBDb `generations.yaml`) |
| `vehicle_variants` | trims/engines beneath a vehicle |
| `ecus` | `vendor` + `model` + `variant` + `ecu_type` + protocol (`Continental EMS2101`, `Toyota 7E0`) |
| `vehicle_ecu_links` | vehicle variant → ECU header (`7E0` engine, `7E1` transmission) |
| `pids` | request/parameter: `mode`, `pid`, `scope` (`generic` for SAE Mode 01/09, `vehicle` for OBDb Mode 21/22), unit, formula, range, OBDb `signal_id`/`path` and the raw formatting descriptor in `fmt_json` |
| `pid_texts` | per-language parameter names |

Nothing in these tables claims a DTC applies to a vehicle. That link, when it exists, is expressed
by a DTC identity with `context_type = 'vehicle_variant'`.

## 3. DTC identity and content

### `dtc_codes` — identity
The centre of the schema. `context_key` is `code|standard|context_type:target` (lower-cased,
ASCII), `UNIQUE`.

| `context_type` | Meaning | Extra column |
| --- | --- | --- |
| `generic` | meaning that holds for every vehicle (SAE/ISO generic layer) | — |
| `manufacturer` | manufacturer-specific meaning | `manufacturer_id` |
| `ecu` | meaning defined by an ECU/control-unit family | `ecu_id` |
| `vehicle_variant` | meaning documented only for one variant | `vehicle_variant_id` |

Consequences visible in release 0.1.0: 12,947 generic / 26,409 manufacturer / 866 ECU identities
over 19,216 distinct codes; `P1690` exists 22 times, once per manufacturer that documents it.

`standard` (`sae_j2012`, `iso_15031_6`, `iso_14229_1`, `manufacturer_specific`, `unknown`) is
*reported*, not inferred from the code prefix. `severity_source` keeps the upstream's own severity
vocabulary; `system`/`subsystem`/`protocol`/`category` are filled when a source provides them.

### `dtc_definitions` — statements
One row per distinct statement per language: `title`, `description`, `content_hash`
(SHA-256 of the normalized text), `is_canonical`, `verification_status`, `confidence`,
`is_translated`, `translation_reviewed`.

* `UNIQUE(dtc_code_id, language, content_hash)` — identical text from two sources is one row with
  two claims; different text is two rows.
* At most one canonical row per `(dtc_code_id, language)` (gate `D005`).
* `verification_status` — see [DATA_DICTIONARY](DATA_DICTIONARY.md#verification-status).

Release 0.1.0: 65,108 definitions (55,575 en, 9,533 de), 14,029 verified, 42,108 source-reported,
8,971 conflicting.

### Content tables
All follow the same pattern: a language-neutral row keyed by a stable `*_key`, plus a `*_texts`
table for human languages. That is what makes Arabic an additive change rather than a migration.

| Table | Key | Notable columns |
| --- | --- | --- |
| `dtc_causes` | `cause_key` | `likelihood` (low/medium/high) — the upstream's own wording, never invented |
| `dtc_symptoms` | `symptom_key` | — |
| `dtc_tests` | `test_key` | `kind` (check, measurement, freeze_frame, drive_cycle, resistance, voltage, visual), `expected`, `requires_tool`, `sequence` |
| `dtc_repairs` | `repair_key` | `difficulty`, `diy_possible`, `cost_min/max` + `currency`, `hours_min/max` |
| `dtc_related_codes` | (`related_code`, `relation_type`) | `related_dtc_code_id` resolved when the code exists, otherwise NULL (gate `D006`) |
| `dtc_components` | `component_key` | affected parts, bilingual labels |
| `dtc_flags` | 1:1 with `dtc_codes` | `mil`, `emissions_relevant`, `drive_cycle_required`, `limp_mode_possible`, plus `risk_level` with `risk_rule_id` and `risk_basis_json` |

`dtc_tests` is empty in release 0.1.0 because no upstream ships procedures (see
[DATA_SOURCES](DATA_SOURCES.md#coverage-summary-of-the-merged-result)). The table, its texts and
its provenance path are implemented and tested.

## 4. Provenance, conflicts, validation, duplicates

### `provenance_claims` — the audit trail
`(entity_type, entity_id, attribute)` + `source_id` + `data_version_id` + `source_record_id` +
`extraction_method` + `is_derived` / `is_translated` + `verification_status` + `extracted_at`.

`entity_type` names a table (`dtc_code`, `dtc_definition`, `dtc_cause`, `dtc_symptom`,
`dtc_repair`, `dtc_related_code`, `dtc_flag`, `dtc_component`, `pid`, `vehicle`, `vehicle_variant`,
`ecu`), `entity_id` its primary key. `extraction_method` distinguishes `connector` (parsed from a
file) from `derived:<rule>` and `human_translation`. `UNIQUE(entity_type, entity_id, attribute,
source_record_id, extraction_method)` keeps re-imports idempotent.

327,369 claims exist in release 0.1.0. Gate `D003` proves that every DTC has at least one and `D008`
that every non-derived claim points at a real `source_records` row.

### `conflicts` / `conflict_evidence`
One conflict per `(code, context, language)` whose competing statements disagree:
`conflict_type` (`definition_disagreement`, `cause_likelihood_disagreement`, `flag_disagreement`),
`attribute`, `summary`, `similarity`, `status` (`needs_review` / `resolved` /
`accepted_difference`), `resolution_note`. Each competing statement is stored in
`conflict_evidence` with its `source_slug` and the claim it came from.

A conflict never deletes a statement: both rows survive with `verification_status = 'conflicting'`
and the canonical row remains the precedence winner.

### `validation_results`
Every rule result of the last build (`rule_id`, `severity`, `passed`, `message`, `entity_type`,
`entity_id`). Import-time results live in `data/staging/*/validation.jsonl`; this table holds the
database-level view so `autodoctor validate` and the manifest can agree.

### `duplicate_groups` / `duplicate_members`
`match_type` is one of:

| `match_type` | Meaning | Action |
| --- | --- | --- |
| `exact_statement` | identical canonical statement in the same `(code, context, language)` | merged into one definition row |
| `near_statement` | similarity above threshold but not identical | **kept separate**, reported |
| `code_context_variants` | same code in several contexts | **not** a duplicate, reported for visibility |

`entity_ref` is `slug:source_record_id` for statements and the `context_key` for codes.

## 5. Releases and translations

* `db_versions` — one row per built version: `sources_json`, `counts_json`, `validation_json`,
  `sha256`, `export_path`, `test_status`, `published_at`.
* `translations` — human-provided translations with `translator`, `reviewer`, `source_url`,
  `reviewed`. Only `reviewed = 1` rows are applied to `dtc_definitions` (as
  `is_translated = 1, translation_reviewed = 1`) and their claim carries
  `extraction_method = 'human_translation'`.

## 6. Views for the client

* `v_dtc_lookup` — one row per `(code, context, language)` with the statement, its status and the
  manufacturer/ECU names. The canonical lookup for the app.
* `v_dtc_summary` — one row per `(code, context)` with `title_en`, `title_ar`, content counts,
  `source_count`, `risk_level`, `mil`, `emissions_relevant`. The app list/search screen.

The app bundle replaces `v_dtc_summary` with a variant that derives `source_count` from the compact
`provenance_summary` table, because the claim matrix itself is not shipped.

## Indexes

| Index | Serves |
| --- | --- |
| `idx_dtc_codes_code` | "which meanings exist for this code" |
| `idx_dtc_codes_context` | filter by context/manufacturer |
| `idx_defs_lang` | language + canonical lookup |
| `idx_related_code` | reverse related-code lookup |
| `idx_claims_entity`, `idx_claims_source` | provenance queries, per-source audits |
| `idx_conflicts_status` | review queue |
| `idx_validation_rule` | quality dashboards |
| `idx_source_records_hash` | raw-record dedupe and integrity checks |

## Size

| Artifact | Size | Contents |
| --- | ---: | --- |
| `db/autodoctor.sqlite` (working) | 147 MB | everything |
| `data/exports/autodoctor-0.1.0.sqlite` | 147 MB | published engineering copy |
| `data/exports/autodoctor-app-0.1.0.sqlite` | 60 MB | app bundle: content tables + `provenance_summary` 199,520 rows, no claim matrix, no raw records |
