# Worked example: P0301 from source files to a diagnostic card

Everything below was executed against the real upstream checkouts on **2026-10-31** and copied
verbatim. Every number and row comes from the database in `data/samples/autodoctor-sample.sqlite`
(a 300-code slice of the public release, committed to this repository), so you can reproduce it.

```
P0301 → "Cylinder 1 Misfire Detected"
        causes (5) · symptoms (4) · repair estimate · 3 components · 5 related codes
        verified by 2 independent lineages (OBDex CC0-1.0, Wal33D MIT)
        7 upstream citations (SAE J2012, GM Mode 6 guide, CA 13 CCR 1968.2, NHTSA TSBs, …)
```

---

## 1. Fetch and inspect the sources

```console
$ autodoctor fetch-sources
{
  "obdex": "cloned",
  "wal33d": "cloned",
  "autodiag": "cloned",
  "obdb": "cloned 5 vehicle repositories"
}

$ autodoctor inspect-sources
[OK] obdex  (OBDex (foerbsnavi/OBDex))
    commit: a9d0220bdb993cd5f545ee762a0531463a2d0fbf  label: a9d0220  dirty: False
    licence: code=MIT data=CC0-1.0 review=approved share_alike=False
    dtc_entries: 9533
[OK] wal33d  (Wal33D dtc-database)
    commit: 04c43d72e7db7197658b6f72fe582c5076d9eee8  label: 04c43d7  dirty: False
    licence: code=MIT data=MIT review=approved share_alike=False
    rows: 18805
    unique_codes: 12128
    ! text lists hold 18826 parseable lines but the compiled SQLite has 18805 rows
[OK] autodiag  (autodiag2/database)
    commit: 11e73fd6d105a071fa472f426d23225344921a19  label: 11e73fd6  dirty: False
    licence: code=GPL-3.0-or-later data=ODbL-1.0 review=pending share_alike=True
    code_files: 28833
[OK] obdb  (OBDb vehicle signal sets)
    commit: obdb:bfe465163ddd7fcdddb6bd564acee89d  label: 5 vehicle repositories  dirty: False
    licence: code=CC-BY-SA-4.0 data=CC-BY-SA-4.0 review=pending share_alike=True
    repositories: 5
    dtc_definitions: 0
```

## 2. Import (raw archive → staging → validation)

```console
$ autodoctor import --all
== obdex
  raw records: 9665  normalized: 9665  files: 9  rejected: 0
  record types: {"dtc": 9533, "pid": 132}
== wal33d
  raw records: 18805  normalized: 18805  files: 1  rejected: 0
== autodiag
  raw records: 31434  normalized: 31434  files: 31434  rejected: 1
  record types: {"dtc": 28833, "ecu": 1085, "vehicle": 1516}
== obdb
  raw records: 1447  normalized: 1447  files: 10  rejected: 0
  record types: {"vehicle": 19, "ecu": 19, "pid": 1409}
```

The one rejected record is `P15O9` (letter O) from autodiag2: it fails blocking rule `V001` and is
quarantined instead of being silently "repaired" into `P1509`.

## 3. Build the public release

```console
$ autodoctor build-db --version 0.4.0 --source-set public
version:        0.4.0
source set:     public
  excluded:     autodiag (legal review pending, ODbL-1.0)
  excluded:     obdb (legal review pending, CC-BY-SA-4.0)
export:         data/exports/autodoctor-0.4.0-public.sqlite
app bundle:     data/exports/autodoctor-app-0.4.0-public.sqlite (52.1 MB)
counts:
  dtc_codes                 19,089
  dtc_codes_distinct        12,412
  definitions               37,871
  causes                    28,334
  symptoms                  26,283
  tests                          0
  repairs                    9,533
  related_codes             32,361
  pids                         132
  conflicts                    503
  conflicts_open               503
  claims                   233,432
  codes_with_arabic              0
release checks:  11/11 passed
  [ok  ] D001_foreign_keys … D011_public_source_set
```

## 4. Look it up

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

Note the second identity: Wal33D documents a *different*, Audi-specific meaning for P0301. The
engine keeps both and shows which one you are reading — code alone is not an identity.

```console
$ autodoctor explain P0301
P0301  [generic]  P0301|sae_j2012|generic:generic
  standard: sae_j2012  protocol: obd2
  * de: Zylinder 1 Fehlzündung erkannt
      status: source_reported (confidence 0.5)
      <- obdex @ a9d0220bdb99 | licence CC0-1.0 | 2026-10-31T21:11:46Z
         file data/generic/P0xxx_enriched.yaml record P0xxx_enriched.yaml#P0301
  * en: Cylinder 1 Misfire Detected
      status: verified (confidence 1.0)
      <- obdex @ a9d0220bdb99 | licence CC0-1.0 | 2026-10-31T21:11:46Z
         file data/generic/P0xxx_enriched.yaml record P0xxx_enriched.yaml#P0301
    en: Cylinder 1 Misfire Detected
      status: verified (confidence 1.0)
      <- wal33d @ 04c43d72e7db | licence MIT | 2026-10-31T21:12:04Z
         file data/dtc_codes.db record P0301|GENERIC|en
  content: dtc_causes=5, dtc_symptoms=4, dtc_tests=0, dtc_repairs=1, dtc_components=3, dtc_related_codes=5
  evidence: 7 upstream citation(s)
    - [reference] sae:J2012
    - [source] https://gsi.ext.gm.com/gmspo/mode6/pdf/2018/18OBDG03A%20Engine%20Diagnostics.pdf
    - [source] https://law.cornell.edu/regulations/california/13-CCR-1968.2
    ... 4 more
```

The two English rows are the same statement with different text length: OBDex adds a paragraph,
Wal33D has the title only. They agree on the headline, so both are `verified` (two independent
lineages), and the richer OBDex row is canonical.

## 5. The same data in SQL

The committed sample contains 300 real codes with everything attached:

```console
$ sqlite3 data/samples/autodoctor-sample.sqlite
```

**Identity** — `code` alone is not a key; `context_key` is.

| id | code | standard | context_type | context_key | category |
|---|---|---|---|---|---|
| 1718 | P0301 | sae_j2012 | generic | P0301\|sae_j2012\|generic:generic | powertrain |

**Definitions** (one row per distinct statement per language)

| language | title | is_canonical | verification_status | confidence |
|---|---|---|---|---|
| de | Zylinder 1 Fehlzündung erkannt | 1 | source_reported | 0.5 |
| en | Cylinder 1 Misfire Detected | 1 | verified | 1.0 |
| en | Cylinder 1 Misfire Detected | 0 | verified | 1.0 |

**Causes** — the upstream's own likelihood, never a frequency vote

| language | likelihood | label |
|---|---|---|
| de | high | Zündspule von Zylinder 1 defekt (Spule, Stecker, Masse) |
| de | high | Zündkerze von Zylinder 1 verschlissen, verrußt, gerissen oder mit falschem Abstand |
| de | medium | Injektor von Zylinder 1 verstopft oder undicht, oder dessen Ansteuerung |
| de | low | Geringe Kompression an Zylinder 1 (Ventil, Ringe, Kopfdichtung) oder örtliche Falschluft |
| de | low | Wasser oder Öl im Kerzenschacht |
| en | high | Ignition coil of cylinder 1 faulty (coil, connector, ground) |
| en | high | Spark plug of cylinder 1 worn, sooted, cracked or wrongly gapped |
| en | medium | Injector of cylinder 1 clogged or leaking, or its control |
| en | low | Low compression on cylinder 1 (valve, rings, head gasket) or local false air |
| en | low | Water or oil in the plug well |

**Symptoms**

| language | text |
|---|---|
| de | Geruch nach unverbranntem Kraftstoff, Mehrverbrauch |
| de | Leistungsverlust, Zögern beim Beschleunigen |
| de | Motorkontrollleuchte an, blinkend bei katalysatorschädigender Rate |
| de | Unruhiger Leerlauf, Ruckeln, Vibrationen |
| en | Check engine light on, flashing at a catalyst-damaging rate |
| en | Loss of power, hesitation |
| en | Rough idle, jerking, vibration |
| en | Smell of unburnt fuel, higher consumption |

**Repair estimate** (OBDex currency is EUR; the app must show it as such)

| difficulty | diy_possible | cost_min | cost_max | currency | hours_min | hours_max |
|---|---|---|---|---|---|---|
| easy | 1 | 30.0 | 800.0 | EUR | 0.3 | 4.0 |

`dtc_repair_texts` is empty for P0301: OBDex publishes effort and cost, not a repair procedure. The
engine does not invent one — procedures are phase-2 authored content (`dtc_tests`).

**Affected components** (OBDex publishes machine keys; the readable label is generated and the
claim is flagged `is_derived = 1`)

| language | label |
|---|---|
| en | Fuel injector cylinder 1 |
| en | Ignition coil cylinder 1 |
| en | Spark plug cylinder 1 |

**Flags and derived risk**

| mil | emissions_relevant | drive_cycle_required | limp_mode_possible | risk_level | risk_rule_id |
|---|---|---|---|---|---|
| 1 | 1 | 1 | 1 | high | risk_flags_v1 |

`risk_basis_json` stores the inputs and the score (4), so the value can be re-derived later.

**Related codes**

| related_code | relation_type |
|---|---|
| P0201 | related |
| P0300 | related |
| P0316 | related |
| P0351 | related |
| P0420 | related |

**Sources and verification** (compact provenance, as shipped in the app bundle)

| slug | data_license | legal_review_status | verification_status |
|---|---|---|---|
| obdex | CC0-1.0 | approved | verified |
| wal33d | MIT | approved | verified |

**Upstream citations** (stored as rows, not buried in a claim)

| kind | url |
|---|---|
| reference | sae:J2012 |
| source | https://gsi.ext.gm.com/gmspo/mode6/pdf/2018/18OBDG03A%20Engine%20Diagnostics.pdf |
| source | https://law.cornell.edu/regulations/california/13-CCR-1968.2 |
| source | https://saabwisonline.com/9-3-9440/2003/dtcs/t8/p0301-00 |
| source | https://static.nhtsa.gov/odi/tsbs/2016/MC-10186907-9999.pdf |
| source | https://static.nhtsa.gov/odi/tsbs/2016/SB-10084296-2280.pdf |
| source | https://static.nhtsa.gov/odi/tsbs/2023/MC-10241133-9999.pdf |

**The summary view the app lists from**

| code | title_en | title_ar | cause_count | symptom_count | test_count | repair_count | source_count | risk_level |
|---|---|---|---|---|---|---|---|---|
| P0301 | Cylinder 1 Misfire Detected | NULL | 5 | 4 | 0 | 1 | 2 | high |

`title_ar` is `NULL` because no source provides Arabic and no reviewed translation exists yet — the
app must show "not translated", never a machine translation.

**Conflicts**: none for P0301 — both sources agree. (A code with disagreement keeps both statements
and gets a conflict row; see `docs/CONFLICT_REVIEW.md`.)

## 6. Reproduce it yourself

```bash
pip install -e .
autodoctor fetch-sources && autodoctor import --all
autodoctor build-db --version 0.4.0 --source-set public
autodoctor search P0301 && autodoctor explain P0301

# or just open the committed sample
sqlite3 data/samples/autodoctor-sample.sqlite \
  "SELECT language, title, verification_status FROM dtc_definitions d
     JOIN dtc_codes c ON c.id = d.dtc_code_id
    WHERE c.code = 'P0301' AND c.context_type = 'generic';"
```
