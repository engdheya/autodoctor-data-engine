# Data dictionary

The controlled vocabularies of the database, and the rules that produce derived values.

## Codes

| Field | Format | Notes |
| --- | --- | --- |
| `code` | `^[PBCU][0-3][0-9A-F]{3}$` | uppercase, no spaces/dashes/zero-width characters |
| `standard` | `sae_j2012`, `iso_15031_6`, `iso_14229_1`, `manufacturer_specific`, `unknown` | as reported by the source; the code prefix alone never decides it |
| `protocol` | free text (`obd2`, `uds`, `kwp2000`, …) | only when the source states it |
| `category` | `powertrain`, `body`, `chassis`, `network`, `unknown` | from the first letter *and* the source's own category field; a mismatch is warning `V002` |

Normalization rules (`normalizers/codes.py`):

* Trim, collapse whitespace, remove zero-width and bidi marks, uppercase.
* Strip scanner noise around the code (`DTC: P0301`, `P0-301`, `[P0301]`).
* **Never repair an identity.** `P15O9` (letter O) stays invalid and is quarantined by `V001`.

## Context

| `context_type` | Target column | Key form |
| --- | --- | --- |
| `generic` | — | `P0301|sae_j2012|generic:generic` |
| `manufacturer` | `manufacturer_id` | `P1690|manufacturer_specific|manufacturer:ford` |
| `ecu` | `ecu_id` | `P1640|manufacturer_specific|ecu:bosch edc16c34` |
| `vehicle_variant` | `vehicle_variant_id` | `P1A2B|manufacturer_specific|vehicle_variant:ford focus 2012 1.6l` |

The key is lower-cased ASCII with whitespace collapsed. `Context` refuses to be constructed without
its target, and `generic` refuses to carry one — both are enforced by the model, not by convention.

Manufacturer labels that are *not* manufacturers (`GENERIC`, `OTHER`, `SAE`, `saej2012.2002`,
protocol names) never become `manufacturers` rows. `OTHER` maps to the manufacturer context with the
display name `Unspecified`, which is why that name appears in the data (2,620 identities from
Wal33D's unassigned bucket).

## Languages

| Column value | Meaning |
| --- | --- |
| `en`, `de`, `ar`, `fr`, `es`, `it`, `pt`, `ru`, `tr`, `nl`, `pl`, `unknown` | ISO 639-1 |

Normalization maps `EN-us`, `en_US`, `eng`, `English` → `en`. **Arabic is not present in any
upstream source**, so release 0.1.0 has 0 Arabic definitions. The engine never machine-translates:

1. `autodoctor export-translation-template` writes a CSV of codes missing a translation.
2. Translators return YAML in `data/translations/ar/<batch>.yaml`.
3. Only entries with `reviewed: true` **and** a `reviewer` are loaded; the rest are reported.
4. The resulting definition has `is_translated = 1`, `translation_reviewed = 1`, and its provenance
   claim has `extraction_method = 'human_translation'` with translator/reviewer in `notes`.

## Verification status

Applies to `dtc_definitions.verification_status`, `provenance_claims.verification_status` and the
content tables.

| Value | Meaning | How it is produced |
| --- | --- | --- |
| `verified` | at least *N* distinct **lineages** state the same thing (byte-equal, or same headline) | merge pass 2; `N = 2` by default |
| `source_reported` | one lineage states it; nothing contradicts it | default |
| `conflicting` | another lineage states something different for the same `(code, context, language)` | conflict pass |
| `unverified` | accepted structural record but no statement at all (e.g. a code with no definition text) | validators |

Lineage, not repository count: autodiag2 declares `obdcodex` as the evidence for 27,967 of its
28,833 files, so `autodiag2 + obdcodex` is one lineage while `autodiag2 + Wal33D` is two.

`confidence` is `min(1.0, lineages × 0.5)`: 0.5 for a single lineage, 1.0 from two up. It is a
display hint derived from the count, not a probability, and it is recomputed on every build.

## Conflicts

| Type | Raised when |
| --- | --- |
| `definition_disagreement` | two lineages give different statements (similarity below the agreement threshold) for the same `(code, context, language)` |
| `cause_likelihood_disagreement` | same cause, different `likelihood` |
| `flag_disagreement` | same code, contradictory `mil` / `emissions_relevant` flags |

`status`: `needs_review` (default) → `resolved` (a human chose, note stored) or
`accepted_difference` (both statements are legitimate, e.g. wording variants across markets).

Identical statements from the same source are counted as `same_source_variants`, **not** conflicts.

## Duplicate kinds

| `match_type` | Rule | Effect |
| --- | --- | --- |
| `exact_statement` | equal `canonical_form(headline)` within `(code, context, language)` | one definition row, several claims |
| `near_statement` | headline/description similarity ≥ threshold, < 1 | reported, both rows kept |
| `code_context_variants` | same code, different context | reported as **not** duplicates |

`canonical_form` lower-cases, strips punctuation and collapses whitespace, so
`Threshold (Bank 1)` ≡ `Threshold Bank 1`. It does not stem or translate.

## Causes, symptoms, tests, repairs

| Category | `*_key` | Values |
| --- | --- | --- |
| cause | ASCII snake_case of the concept (`vacuum_leak`) | `likelihood`: `low` / `medium` / `high` |
| symptom | ASCII snake_case (`rough_idle`) | — |
| test | ASCII snake_case (`check_freeze_frame`) | `kind`: `check`, `measurement`, `freeze_frame`, `drive_cycle`, `resistance`, `voltage`, `visual`, `other`; `expected`, `requires_tool`, `sequence` |
| repair | ASCII snake_case (`replace_ignition_coil`) | `difficulty`: `easy` / `medium` / `hard` / `shop_only`; `diy_possible` 0/1; `cost_min`/`cost_max` + `currency`; `hours_min`/`hours_max` |

A key groups the same concept across sources; the human wording lives in the `*_texts` tables, one
row per language. Two sources describing "vacuum leak" and "intake leak" stay two causes — the
engine does not merge them by similarity.

## Risk level

`dtc_flags.risk_level` is **derived**, never copied from an upstream. Rule id: `risk_flags_v1`.

| Inputs (score) | Value | Explanation stored |
| --- | --- | --- |
| no flags at all (0) | `NULL` | "no severity flags available from any source" |
| MIL only (1) | `low` | "MIL only" |
| 2–3 (MIL + emissions, or limp mode alone) | `medium` | "MIL plus emissions or drivability impact" |
| 4 (MIL + emissions + limp mode) | `high` | "MIL + emissions relevance + possible limp mode" |

Scoring: MIL `+1`, emissions relevant `+1`, limp mode possible `+2`; `drive_cycle_required` is
recorded in the basis but does not change the level. `critical` is reserved in the schema and is
never produced by this rule (nothing in the sources supports it).

`risk_basis_json` stores the inputs, the score, the rule id and the explanation, and every derived
value also gets a `provenance_claims` row with `extraction_method = 'rule:risk_flags_v1'` and
`is_derived = 1`. Release 0.1.0: 2,028 high, 5,182 medium, 1,384 low, `NULL` for 939 identities
without flags.

## PIDs and parameters

| Field | Meaning |
| --- | --- |
| `mode` | `01`, `09` (generic SAE) or `22` (OBDb vehicle parameters) |
| `pid` | the PID/parameter id (`0C`, `0102`, …) |
| `scope` | `generic` (all vehicles) or `vehicle` (a specific vehicle's signal set) |
| `unit`, `formula`, `range_min`, `range_max` | when the source provides them |
| `signal_id`, `path`, `fmt_json` | OBDb signal identity, path inside the signalset, and its raw `fmt{len,bix,mul,div,max,unit}` descriptor |

OBDb's `filter` (customer-facing) and `dbgfilter` (engineering) are preserved in `fmt_json` rather
than interpreted, because they are gateway filters, not data.

## Related codes

`relation_type` is `related` unless a source states otherwise (`variant_of`, `superseded_by`).
`related_dtc_code_id` is filled only when the related code exists in the database; the raw
`related_code` text is always kept. Gate `D006` reports unresolved relations as informational —
there are 0 in release 0.1.0.

## Vehicles, ECUs

| Field | Meaning |
| --- | --- |
| `vehicles.year_start` / `year_end` | model years covered by a generation, inclusive |
| `vehicle_variants.name` | trim/engine label |
| `ecus.name` | `<vendor> <model>` or the CAN header when no vendor is known (`Toyota 7E0`) |
| `vehicle_ecu_links.header` | CAN arbitration id (`7E0` engine, `7E1` transmission) |
| `vehicle_ecu_links.ecu_type` | `engine`, `transmission`, `abs`, … as declared by the signalset |

## Provenance fields

| Field | Meaning |
| --- | --- |
| `entity_type` / `entity_id` | what the claim is about (`dtc_definition` / 12345) |
| `attribute` | which part of it (`text`, `cause`, `flag`, `related_code`, …) |
| `source_id`, `data_version_id` | repository and exact commit |
| `source_record_id` | the immutable upstream record (`file#code`) |
| `extraction_method` | `connector`, `derived:<rule>`, `human_translation` |
| `is_derived`, `is_translated` | explicit so a client can filter them |
| `value_hash` | reserved for value-level dedupe (currently NULL by design) |
| `extracted_at`, `notes` | when and any human-facing context |
