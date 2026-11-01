# Flutter integration guide (database contract)

The app ships one SQLite file and reads it locally. This guide is the contract: what to ship, how to
open it, which views to query, what each costs, and how to prove the file is intact on the device.

Everything below was executed against the real release-candidate artifact:

```
data/exports/autodoctor-app-0.5.0-rc1-public.sqlite   56,840,192 bytes
sha256 4037a98f75df…   (full value in the manifest)
13 views · 30 tables · integrity_check = ok · foreign_key_check = empty
```

## 1. Ship this file

| File | Size | Use |
| --- | ---: | --- |
| `autodoctor-app-<version>-public.sqlite` | 56.8 MB | **ship** (OBDex + Wal33D, licence-cleared) |
| `autodoctor-app-<version>.sqlite` | 71.2 MB | private edition, internal only |
| `autodoctor-<version>-public.sqlite` | 105.8 MB | engineering DB: claim matrix, raw-record links |

The bundle carries content + compact provenance (`provenance_summary`, one row per fact per source).
It has no claim matrix, no raw records and no validation log.

## 2. Opening it

```dart
final db = await openDatabase(
  path,
  readOnly: true,          // the client never writes
  singleInstance: true,
);
await db.execute('PRAGMA foreign_keys = ON');
```

Recommendations: copy the asset to application support on first launch, compare the file size (or a
stored SHA-256) before opening, and never migrate knowledge into the app - a new dataset is a new
file (see `DATABASE_UPDATE_GUIDE.md`).

## 3. Query contract (13 views)

| View | One row per | Use |
| --- | --- | --- |
| `v_dtc_search` | DTC identity | list + search screen, carries `content_tier`, counts, risk |
| `v_dtc_summary` | DTC identity | the diagnostic card (same as above, phase-1 shape) |
| `v_dtc_lookup` | definition | every statement of an identity, both languages |
| `v_dtc_causes` | cause × language | "possible causes" with the source's own likelihood |
| `v_dtc_symptoms` | symptom × language | "symptoms" |
| `v_dtc_repairs` | repair × language | "repair recommendations" incl. difficulty/cost/hours |
| `v_dtc_tests` | procedure × language | inspection procedures (**empty in this release**) |
| `v_dtc_related` | related code | "see also" |
| `v_dtc_provenance` | fact × source | "where does this come from", licence, commit |
| `v_dtc_conflicts` | conflict | "sources disagree" banner |
| `v_manufacturers` | manufacturer | manufacturer picker, with code/vehicle counts |
| `v_pids` | PID | live-data catalogue (names EN/AR, formula, range) |
| `v_vehicles` | vehicle | **empty in this release** (no licence-cleared vehicle data) |

A build whose bundle lacks any of them is refused at build time (`_verify_views`), and the tests
assert each view is selectable.

## 4. Search recipes

`code` is stored uppercase, without spaces.

```sql
-- exact: P0301, p0301 (normalise in Dart: input.trim().toUpperCase().replaceAll(' ', ''))
SELECT * FROM v_dtc_search WHERE code = ? AND context_type = 'generic';

-- every meaning of one code (P1690 exists 34 times, once per manufacturer)
SELECT code, context_type, manufacturer, title_en, content_tier
FROM v_dtc_search WHERE code = ? ORDER BY context_type, manufacturer;

-- prefix / browse
SELECT code, title_en FROM v_dtc_search WHERE code LIKE 'P03%' LIMIT 50;

-- by name (English today; Arabic when reviewed translations exist)
SELECT code, title_en FROM v_dtc_search WHERE title_en LIKE '%misfire%' LIMIT 50;

-- full card
SELECT * FROM v_dtc_search WHERE code = 'P0301' AND context_type = 'generic';
SELECT language, label, likelihood FROM v_dtc_causes
 WHERE dtc_code_id = ? ORDER BY likelihood DESC;
SELECT language, text FROM v_dtc_symptoms WHERE dtc_code_id = ?;
SELECT language, text, difficulty, cost_min, cost_max, hours_min, hours_max
  FROM v_dtc_repairs WHERE dtc_code_id = ?;
SELECT source_slug, data_license, commit_sha, verification_status
  FROM v_dtc_provenance WHERE entity_type = 'dtc_code' AND entity_id = ?;
```

**Never show a manufacturer statement as a generic definition.** Filter `context_type` explicitly:
`generic` for the SAE J2012 meaning, `manufacturer` (with `manufacturer`) for brand-specific ones.

## 5. Content tier (mandatory in the UI)

`v_dtc_search.content_tier` is `diagnosis_ready` when the identity has at least one cause, otherwise
`definition_only`. In this release that is **9,533 of 19,089 identities**. The app must label the
second tier as "definition only - no diagnostic content available for this code". Showing a bare
title as if it were a diagnosis is the failure mode this field exists to prevent.

## 6. Measured cost (x86_64, SQLite 3.40.1, warm page cache)

| Query | Median |
| --- | ---: |
| open + first query | 0.33 ms |
| exact code (indexed) | 0.01 ms |
| exact code, lowercase input | 0.02 ms |
| prefix `P03%` | 0.17 ms |
| causes / symptoms / repairs of one code | 0.01 ms |
| provenance of one code | < 0.01 ms |
| manufacturer list (50) | 0.32 ms |
| PID list (50) | 0.04 ms |
| `title_en LIKE '%misfire%'` (full scan of 19k rows) | 10.2 ms |
| `title_en LIKE '%sensor%'` (count, worst case) | 17.8 ms |

These are desktop numbers; a mid-range Android device is typically 2-5x slower on cold I/O. Name
search is the only expensive query (no FTS by design - see below) and stays well under a frame
budget at this size.

**No FTS on purpose.** FTS5 is present in `sqlite3_flutter_libs` but not guaranteed in the platform
SQLite of older Android images; a bundled file that fails to open on a customer's phone is worse than
a 10 ms scan. If name search becomes the dominant interaction, generate an FTS4 companion table in a
*separate* build variant and gate it by a runtime capability check.

## 7. Verification on the device

```dart
final integrity = await db.rawQuery('PRAGMA integrity_check');
final fkViolations = await db.rawQuery('PRAGMA foreign_key_check');
final views = await db.rawQuery(
  "SELECT name FROM sqlite_master WHERE type='view' ORDER BY name");
```

Expected: `integrity_check` = `ok`, `foreign_key_check` = no rows, 13 views. Run this once after the
first copy and cache the result; a failure means the asset was truncated, not that the data is wrong.

## 8. What the app must not claim

* No Arabic text in this release (0 reviewed translations).
* No inspection procedures (`v_dtc_tests` is empty) - do not render an empty "steps" section as if
  the data were missing at runtime.
* No vehicle/engine/ECU applicability (`v_vehicles`, ECU contexts are empty); vehicle-based search
  must be hidden, not shown empty.
* No severity beyond the documented risk rule: `risk_level` comes from `risk_flags_v1`
  (`risk_basis_json` explains it) for generic codes only.
