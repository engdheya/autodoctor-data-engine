# Flutter integration

The app ships a SQLite file and reads it locally. No network is required to answer "what does
P0301 mean, where does it come from, and how sure are we".

## Which file to ship

| File | Size | Use |
| --- | ---: | --- |
| `data/exports/autodoctor-app-<version>.sqlite` | 60 MB | **ship this** |
| `data/exports/autodoctor-<version>.sqlite` | 147 MB | engineering only: raw record links, claim matrix, validation log |

The app bundle contains every content table, `provenance_summary` (one row per fact + source) and
the two views. It does **not** contain `provenance_claims`, `source_records`, `source_files`,
`validation_results` or duplicate evidence — that is where the other 87 MB went.

## Installation

1. Put the bundle in assets (`assets/db/autodoctor-app-0.1.0.sqlite`) for the first run.
2. On start, copy it to the application support directory if it is missing or older than the
   version stored in `db_versions`.
3. Open with `sqflite` (or `sqlite3` + `drift`):

```dart
final dir = await getApplicationSupportDirectory();
final db = await openDatabase(p.join(dir.path, 'autodoctor.sqlite'), readOnly: true);
```

`PRAGMA foreign_keys` is already `ON` in the file; the app only ever reads.

## Queries the UI needs

**Search by code** (partial input works because of `idx_dtc_codes_code`):

```sql
SELECT * FROM v_dtc_summary
WHERE code LIKE ? || '%'
ORDER BY length(code), code
LIMIT 30;
```

**All meanings of a code** — the P1690 case, where one code has 22 meanings:

```sql
SELECT code, context_type, manufacturer, title_en, title_ar, risk_level, source_count
FROM v_dtc_summary
WHERE code = ?
ORDER BY CASE context_type WHEN 'generic' THEN 0 WHEN 'manufacturer' THEN 1
                           WHEN 'ecu' THEN 2 ELSE 3 END, manufacturer;
```

Show the generic meaning first, then group the rest under "manufacturer specific". Never present
the first row as *the* meaning.

**Diagnostic card:**

```sql
-- statement(s)
SELECT d.language, d.title, d.description, d.verification_status, d.is_canonical
FROM dtc_definitions d JOIN dtc_codes c ON c.id = d.dtc_code_id
WHERE c.context_key = ? ORDER BY d.language, d.is_canonical DESC;

-- causes with the source's own likelihood
SELECT ct.language, ct.label, x.likelihood
FROM dtc_causes x JOIN dtc_cause_texts ct ON ct.cause_id = x.id
WHERE x.dtc_code_id = ? ORDER BY
  CASE x.likelihood WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, ct.label;

-- what to check (empty today, populated by phase 2 content)
SELECT tt.language, tt.text, t.kind, t.expected, t.requires_tool
FROM dtc_tests t JOIN dtc_test_texts tt ON tt.test_id = t.id
WHERE t.dtc_code_id = ? ORDER BY t.sequence;

-- repair effort
SELECT rt.language, rt.text, r.difficulty, r.diy_possible, r.cost_min, r.cost_max,
       r.currency, r.hours_min, r.hours_max
FROM dtc_repairs r JOIN dtc_repair_texts rt ON rt.repair_id = r.id
WHERE r.dtc_code_id = ?;

-- flags and risk
SELECT mil, emissions_relevant, drive_cycle_required, limp_mode_possible,
       risk_level, risk_rule_id FROM dtc_flags WHERE dtc_code_id = ?;

-- "which sources say this" (compact provenance)
SELECT source_name, data_license, commit_sha, record_count, verification_status
FROM provenance_summary
WHERE entity_type = 'dtc_code' AND entity_id = ?
ORDER BY source_name;
```

**Related codes:**

```sql
SELECT related_code, relation_type FROM dtc_related_codes WHERE dtc_code_id = ?;
```

**Parameters for a vehicle** (OBDb data):

```sql
SELECT v.make_or_model, p.mode, p.pid, pt.name, p.unit, p.signal_id
FROM vehicle_variants vv
JOIN vehicles v ON v.id = vv.vehicle_id
JOIN manufacturers m ON m.id = v.manufacturer_id
...
```

(the app bundle keeps `vehicles`, `vehicle_variants`, `ecus`, `vehicle_ecu_links`, `pids`,
`pid_texts`; join through `vehicle_ecu_links` to know which CAN header to ask.)

## UI rules that protect the data's honesty

| Database state | What the UI must do |
| --- | --- |
| `verification_status = 'verified'` | show normally, optionally with "confirmed by N sources" |
| `source_reported` | show normally, no source badge beyond "reported by <source>" |
| `conflicting` | show a visible "sources disagree" affordance that lists both statements |
| `title_ar` is NULL | show English, plus a clear "not yet translated" marker — never a machine translation |
| `risk_level` NULL | show no risk badge at all, not "low" |
| `test_count = 0` | do not claim a "check this" section exists; offer the causes instead |
| multiple contexts for one code | default to `generic`, let the user switch by make/ECU, and say which context is shown |

The bundle stores `risk_rule_id`; when the rule version changes, the UI should not silently compare
old and new values.

## Licence footer

The bundle carries `data_sources` rows with `data_license`, `attribution_required` and
`share_alike`. Render an "About the data" screen from that table plus the attribution text in
[LICENSES](LICENSES.md). This is a legal requirement for Wal33D (MIT), autodiag2 (ODbL) and OBDb
(CC-BY-SA), not a nicety.

## Updates

1. Server (or CDN) publishes `autodoctor-app-<version>.sqlite` + `manifest.json`.
2. App compares `db_versions.version` with the remote one.
3. Download to a temp file, verify the manifest's SHA-256, close the old database, atomically
   rename, reopen. Keep the previous file for one release so a corrupt download is recoverable.
4. Deletions never happen user-side: a code that disappears upstream is still in the previous
   bundle, and `detect-changes` reports it to the maintainers instead of the app.
