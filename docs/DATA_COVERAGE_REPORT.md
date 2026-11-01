# Data coverage report — release candidate 0.5.0-rc1

**Artifact:** `data/exports/autodoctor-0.5.0-rc1-public.sqlite` (105,771,008 bytes,
`sha256 4faee8dbddbd1cb9cec036b2df3e579954ba26911df99446e3e2e094c61045b2`)
**Built:** 2026-11-01T17:26:57Z · **schema:** 3 · **source set:** public
**Engine commit:** `d198639`

This file is generated from the artifact above by `autodoctor coverage --write`; do not edit it by
hand. The machine-readable twin is `data/reports/coverage.json`.

Generated: 2026-11-01T17:28:43Z

Every number is a query against the built database. Ratios print their denominator: the
population we declare support for is stated first, so a percentage can never be read
against a denominator that was quietly narrowed.

## Declared scope

**Supported:**
* DTC identities present in the licence-cleared sources (generic OBD-II / SAE J2012 and manufacturer-specific codes from Wal33D)
* English titles and descriptions
* causes, symptoms, repairs, related codes and risk flags where the source provides them
* compact provenance for every fact (source, commit, licence, verification status)

**Explicitly not supported (and why):**
* Arabic definitions (no reviewed translation exists yet - see ARABIC coverage)
* diagnostic inspection procedures (no licensed source; table exists, content does not)
* vehicle / model / engine / ECU applicability (no licence-cleared vehicle dataset)
* UDS DIDs and proprietary PIDs (not imported)
* country- or market-specific statements (no source documents them)

## DTC population

| Dimension | Count |
| --- | ---: |
| DTC identities (code + context) | 19,089 |
| Distinct codes | 12,412 |
| — context `generic` | 9,699 |
| — context `manufacturer` | 9,390 |
| — family B | 1,599 |
| — family C | 1,133 |
| — family P | 14,822 |
| — family U | 1,535 |
| Manufacturer contexts | 9,390 |
| Manufacturers with codes | 33 |
| ECU contexts | 0 |
| Vehicle-variant contexts | 0 |

## Content coverage per identity

Denominator: **19,089 identities** the database ships.

| Field | Identities | Denominator | Coverage | |
| --- | ---: | ---: | ---: | --- |
| with_english_definition | 19,089 | 19,089 | 100.0% | `####################` |
| with_description | 9,533 | 19,089 | 49.9% | `##########..........` |
| with_causes | 9,533 | 19,089 | 49.9% | `##########..........` |
| with_symptoms | 7,443 | 19,089 | 39.0% | `########............` |
| with_tests | 0 | 19,089 | 0.0% | `....................` |
| with_repairs | 9,533 | 19,089 | 49.9% | `##########..........` |
| with_related_codes | 7,203 | 19,089 | 37.7% | `########............` |
| with_risk_level | 8,594 | 19,089 | 45.0% | `#########...........` |

**Diagnosis-ready identities** (have at least one cause): **9,533** of 19,089.

A definition without causes, symptoms or repairs is a *label*, not a diagnosis. Those rows
are counts in this table, never presented in the app as diagnostic advice.

## Vehicle coverage

| Table | Rows |
| --- | ---: |
| manufacturers | 33 |
| vehicles | 0 |
| vehicle variants | 0 |
| ECUs | 0 |
| vehicle ↔ ECU links | 0 |
| DTCs with an ECU context | 0 |
| DTCs with a vehicle context | 0 |

> No vehicle or ECU rows exist in this edition: no licence-cleared source provides
> them. Vehicle-based search is therefore **not supported** and must not be shown as
> a feature. See the accepted scope above.

## PID coverage

| Metric | Count | Denominator | Coverage |
| --- | ---: | ---: | ---: |
| PIDs with an English name | 132 | 132 | 100.0% |
| PIDs with an Arabic name | 0 | 132 | 0.0% |
| PIDs with a scaling formula | 99 | 132 | 75.0% |
| PIDs with min and max | 99 | 132 | 75.0% |
| PIDs with a unit | 132 | 132 | 100.0% |

By scope: `generic` 132

## Diagnostic procedures

* procedures: **0**
* procedures with text: 0
* codes with a procedure: 0
* ordered steps: 0

> **Zero procedures.** No licence-cleared source ships inspection procedures and this
> project does not author them from memory. The schema, loader, gates and UI contract
> exist; the content does not. The app must not claim procedure coverage.

## Language coverage

| Metric | Count | Denominator | Coverage |
| --- | ---: | ---: | ---: |
| English definitions | 28,338 | — | — |
| Arabic definitions | 0 | 28,338 English definitions | 0.0% |
| Identities with Arabic | 0 | 28,338 English definitions | 0.0% |
| Reviewed Arabic translations | 0 | 0 Arabic definitions | - |
| Other languages (source-provided) | 9,533 | — | — |

Arabic coverage of the identity population: **0 / 19,089**

## Conflicts

| Metric | Count |
| --- | ---: |
| conflicts | 503 |
| open (`needs_review`) | 503 |
| codes affected | 503 |
| definitions flagged `conflicting` | 1,006 |
| type `definition_disagreement` | 503 |

## Provenance

| Metric | Count |
| --- | ---: |
| sources | 2 |
| claims | 233,432 |
| evidence citations | 32,944 |
| definitions from 2+ sources | 0 |
| identities from 2+ sources | 9,249 |

Claims per source: `obdex` 177,017, `wal33d` 56,415

## What may be claimed publicly

* 19,089 DTC identities / 12,412 distinct codes
* 9,533 of them carry causes
* 0 carry Arabic, 0 carry a procedure, 0 carry a vehicle link
* the rest must be described in the app as *definition only*

