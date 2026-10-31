# Data sources — what they actually contain

All figures below were measured by `autodoctor inspect-sources` / `autodoctor import` against the
commits listed. The engine does not trust a repository's README: numbers here come from parsing
the files.

| Source | Commit | Data licence | DTC records | Unique codes | Languages | Content |
| --- | --- | --- | ---: | ---: | --- | --- |
| [OBDex](https://github.com/foerbsnavi/OBDex) | `a9d0220bdb993cd5f545ee762a0531463a2d0fbf` (2026-10-19) | CC0-1.0 | 9,533 | 9,533 | en, de | title, description, components, causes + likelihood, symptoms, repair difficulty/cost/hours, MIL/emissions/limp flags, related codes, 23 364 source URLs |
| [Wal33D dtc-database](https://github.com/Wal33D/dtc-database) | `04c43d72e7db7197658b6f72fe582c5076d9eee8` (2026-02-16) | MIT | 18,805 rows | 12,128 | en | one-line description per (code, manufacturer); generic + 33 manufacturer contexts |
| [autodiag2/database](https://github.com/autodiag2/database) | `11e73fd6d105a071fa472f426d23225344921a19` (2026-08-19) | ODbL-1.0 / DbCL-1.0 | 28,833 files | 16,674 | en | definition line, brand/ECU context, protocol, standard, evidence, plus ECU and vehicle metadata |
| [OBDb](https://github.com/OBDb) (org) | per repository, e.g. `2c08cfe1d128…` | CC-BY-SA-4.0 | 0 | 0 | en | vehicle generations, ECU CAN headers, Mode 21/22 parameters |

---

## 1. OBDex — the semantic backbone

**Layout.** `data/generic/{P0,P2,P3,U0,U3,B0,C0}xxx_enriched.yaml` — one YAML list per family,
plus `data/pids/mode01.yaml` and `mode09.yaml`, and JSON Schemas under `schema/`.

**Observed keys:** every one of the 9,533 entries has `code`, `category`, `title`, `description`,
`affected_components`, `common_causes`, `repair`, `flags`, `references`, `sources`; 7,443 also have
`symptoms`, 7,203 `related_codes`, 3,000 `reviewed`.

**What the engine takes:** everything, kept structured. Titles and descriptions become per-language
definitions; `common_causes` (with `likelihood` high/medium/low) become `dtc_causes` rows with
bilingual labels; `symptoms` become `dtc_symptoms` with bilingual texts; the single `repair` object
becomes a repair estimate with difficulty, DIY flag, EUR cost range and hour range; `flags` drive
the derived risk level; `related_codes` are normalized and linked; `sources` become evidence URLs.

**What it does not have:** manufacturer-specific codes (by design — the project calls them vendor
IP), test procedures, Arabic.

**Quality observations:**

* The `code.schema.json` pattern is `^[PBCU][0-3][0-9A-F]{3}$`; all 9,533 codes satisfy it.
* `applies_to` is declared in the schema but never used in the current data, so no OBDex record
  contributes a vehicle link. The engine records this as "no vehicle evidence", not as "applies to
  all vehicles".

## 2. Wal33D dtc-database — coverage and manufacturer contexts

**Layout.** `data/dtc_codes.db` (SQLite, table `dtc_definitions(code, manufacturer, description,
type, locale, is_generic, source_file)`), the raw `data/source-data/*_codes.txt` lists it was built
from, and a copy of the database inside the Android library assets.

**What the engine takes:** every row, with `manufacturer = GENERIC` mapped to the generic context
and every other label mapped through the alias table. `is_generic` is respected even when it
contradicts the code prefix.

**Quality observations (measured):**

* 18,805 rows, 12,128 unique codes, 34 manufacturer labels, English only.
* **198 codes appear both as generic and as manufacturer-specific.** `P0420` is generic "Catalyst
  System Efficiency Below Threshold Bank 1" but Audi-specific "Inefficient Catalytic Converter(s),
  Defective Front or Rear Oxygen Sensor(s), Misfiring engines". Both are kept, in two contexts.
* **`P1690` has 22 different meanings** (Ford "Wastegate Solenoid Circuit Malfunction", BMW
  "Malfunction Indicator Lamp MIL Electrical", Chrysler "Fuel Injection Pump CKP Sensor Does Not
  Agree With ECM CKP Sensor", …). This single code is the reason `code` is not a unique key.
* The compiled database has **18,805 rows while the raw text lists parse to 18,826 lines** — the
  build in the upstream repository is not reproducible from the files it ships. The engine records
  the discrepancy as an inspection warning and imports the compiled database (the richer of the two).
* 59 generic rows use manufacturer-specific prefixes (e.g. `B1317`), surfaced as validation warning
  `V020` rather than silently reclassified.
* No causes, symptoms, tests or repair data at all.

## 3. autodiag2/database — context and protocol metadata

**Layout.** `data-src/ecu/generic/<brand>/codes/<CODE>.yml` for brand scopes,
`data-src/ecu/generic/saej2012.2002/codes/*.yml` for the generic layer,
`data-src/ecu/<vendor>/<ecu_model>/codes/<CODE>.yml` for ECU scopes (28,833 code files), plus
`data-src/ecu/**/def.yml` ECU metadata (1,149 files, of which 1,085 declare a concrete ECU type) and
`data-src/vehicle/<Make>/<Model>/def.yml` (1,673 files, of which 157 declare a complete vehicle
definition).

**Field population (measured over all 28,833 files):** only seven keys are ever populated —
`code`, `definition`, `created`, `updated`, `protocol`, `standard` (100 % each) and `evidence`
(99.8 %). Everything else the schema allows (`system`, `subsystem`, `category`, `description`,
`severity`, `mil`, `related_code`, `detection_condition`, `causes`, `repairs`) is **absent from
real records**; the fixtures exercise those paths because the schema allows them.

**What the engine takes:** the code, the definition line, the *context* (brand or ECU), protocol
(`obd2`), standard (`saej2012.2002` → `sae_j2012`), and the evidence. Where a record does have
causes, detection conditions or links (a handful), they are imported in full.

**Quality observations:**

* 28,833 files describe 16,674 unique codes: the same code appears in many contexts, which is the
  normal shape of a DTC table and the reason identity includes the context.
* One invalid code exists upstream: **`P15O9`** (letter O instead of zero, Land Rover). It fails
  blocking rule `V001` and is quarantined — it is not silently "repaired" into `P1509`.
* **Evidence lineage matters:** 27,967 of 28,833 files cite `obdcodex` as their evidence; the rest
  mostly cite web pages (819 cite a single Citroën error-table document). The
  engine therefore assigns autodiag2 the lineage `obdcodex`, and corroboration from autodiag2 plus
  Wal33D counts as *two* lineages, while autodiag2 plus obdcodex would count as one.
* Every file declares `standard: [saej2012.2002]`, including `P1xxx` manufacturer codes, so the
  declared standard is stored as reported and the vendor scope is carried by the context instead.

## 4. OBDb — vehicle, ECU and parameter context, **no DTCs**

**Layout.** One GitHub repository per vehicle: `signalsets/v3/default.json`
(`{"ecu": [{"hdr": "7E0", "type": "engine"}], "commands": [...]}`), `generations.yaml`,
`tests/test_cases/**` (recorded ISO-TP responses used by their own CI), `LICENSE`
(CC-BY-SA-4.0). Around 40 vehicle repositories exist at the time of writing.

**Why it is in the project:** the task asks for vehicles, ECUs, parameters and "do not assume a
code applies to a car without evidence". OBDb supplies exactly that context — which CAN header
carries which ECU, which Mode 21/22 parameters a vehicle exposes, which model years a generation
covers — and supplies **no DTC definitions at all**.

**What the engine takes:**

* `vehicles` + `vehicle_variants` from `generations.yaml` (`name`, `start_year`, `end_year`,
  `description`).
* `ecus` + `vehicle_ecu_links` from the signalset `ecu` array (header + ECU type).
* `pids` with `scope = 'vehicle'` from `commands[].signals[]` (mode, PID, signal id, path, unit,
  formatting descriptor).
* Repository name → manufacturer/model via longest-known-manufacturer-prefix matching
  (`Mercedes-Benz-EQS-Class-Sedan` → Mercedes-Benz / EQS-Class-Sedan).

**Consequences, stated explicitly:**

* `dtc_codes.context_type = 'vehicle_variant'` is **0** in release 0.1.0. No DTC is linked to a
  vehicle, because none of the four sources documents such a link for the codes we hold.
* DTC count contributed by OBDb: **0**.
* OBDb is a multi-repository source; the engine records a synthetic version
  (`obdb:<hash of all repository commits>`) and keeps each repository's own commit in the
  inspection report, so a rebuild can reproduce the exact set.

## Coverage summary of the merged result

| Dimension | Value |
| --- | ---: |
| Generic identities (all-vehicle meaning) | 12,947 |
| Manufacturer identities | 26,409 |
| ECU identities | 866 |
| Vehicle-variant identities | 0 |
| Codes with causes | 9,533 |
| Codes with repairs | 9,533 |
| Codes with tests | 0 |

The two gaps are genuine, not bugs:

* **Tests / inspection procedures.** No upstream provides them. `dtc_tests` exists, is populated
  when a source has data (the fixture suite proves the path), and stays empty for real sources. The
  intended next step is human-authored, reviewed procedure files (same review gate as translations)
  — see [DEVELOPMENT_PLAN](DEVELOPMENT_PLAN.md).
* **Arabic.** No upstream provides Arabic. See [DATA_DICTIONARY](DATA_DICTIONARY.md#languages).
