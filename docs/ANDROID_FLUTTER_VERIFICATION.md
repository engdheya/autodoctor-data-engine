# Android / Flutter verification — release candidate 0.6.0-rc1

This document states exactly what has been **measured** on the bundle and what still
requires a device run. Nothing below is projected.

## 1. What was executed here

Command:

```bash
python flutter_harness/tool/verify_contract.py \
    --database data/exports/autodoctor-app-0.6.0-rc1-public.sqlite \
    --out data/reports/contract-verification.json
```

Measured output (full machine-readable copy in `data/reports/contract-verification.json`):

| Check | Result |
| --- | --- |
| `PRAGMA integrity_check` | `ok` |
| `PRAGMA foreign_key_check` | 0 violations |
| Views exposed to the client | 13 (`v_dtc_search`, `v_dtc_lookup`, `v_dtc_causes`, `v_dtc_symptoms`, `v_dtc_repairs`, `v_dtc_tests`, `v_dtc_related`, `v_dtc_provenance`, `v_dtc_conflicts`, `v_dtc_summary`, `v_manufacturers`, `v_pids`, `v_vehicles`) |
| Bundle size | 56,840,192 bytes |

Contract queries against that file:

| # | Scenario | Result |
| --- | --- | --- |
| 1 | Generic lookup `P0301` | 1 row — "Cylinder 1 Misfire Detected", tier `diagnosis_ready`, 5 causes / 4 symptoms / 1 repair, risk `high`, 0.36 ms |
| 2 | Manufacturer context `P1690` | distinct per-manufacturer meanings (Acura "Traction Control System STB Line Failure", BMW "MIL Electrical", Ford "Wastegate Solenoid Circuit Malfunction", …) — no single meaning is picked |
| 3 | Vehicle search | 0 rows — **no vehicle data in this build**, the UI must hide the selector |
| 4 | Code without diagnostics | e.g. `B0081`, tier `definition_only`, 0 causes — must render as definition only |
| 5 | Arabic titles | 0 — no reviewed Arabic exists, so the UI must show EN only |
| 6 | Provenance for `P0301` | source `obdex`, licence `CC0-1.0`, commit `a9d0220b…`, status `verified` |
| 7 | Inspection procedures | 0 rows — procedure view is empty in this build |
| 8 | Conflicts | 503 rows, 503 `needs_review` |

Every number above matches `data/exports/autodoctor-0.6.0-rc1-public.manifest.json`
for the same artifact (12/12 release checks passed, gate **D012 overridden** on this
candidate — recorded in the manifest's `gate_overrides`).

## 2. The Flutter harness

`flutter_harness/` is a real, runnable Flutter project that executes the same SQL
through `sqflite`. It is deliberately small: it is an integration harness, not the app.

- `lib/contract.dart` — `DbContract` with `lookup`, `generic`, `causes`, `symptoms`,
  `repairs`, `procedures`, `provenance`, `vehicleCount`, `arabicCount`, `views`,
  `integrityCheck`, and code normalisation (`p 0301` → `P0301`).
- `test/contract_test.dart` — host-side test (`flutter test` with
  `--dart-define=DB=...`), asserts `ok` integrity, 13 views, `P0301`
  diagnosis-ready, non-empty causes/symptoms/repairs, provenance carrying
  licence **and** commit, and that vehicles/Arabic are 0 rather than invented.
- `integration_test/contract_device_test.dart` — the same assertions on an Android
  device or emulator.
- `tool/verify_contract.py` — the runner used above; it is the record of what CI and
  the release notes cite.

## 3. What is still unverified, and why

There is no Flutter SDK, Android SDK, emulator or physical device in the build
sandbox, so the on-device step could not be executed here. To close it:

```bash
# on a machine with the Android SDK / a connected device
cd flutter_harness
flutter pub get
flutter test --dart-define=DB=/abs/path/autodoctor-app-0.6.0-rc1-public.sqlite
adb push ../data/exports/autodoctor-app-0.6.0-rc1-public.sqlite \
         /data/local/tmp/autodoctor-app.sqlite
flutter test integration_test/contract_device_test.dart \
         --dart-define=DB=/data/local/tmp/autodoctor-app.sqlite
```

**Status: NOT DONE.** This is one of the blockers for `v1.0.0`; the release stays at
`0.6.0-rc1` until this run is attached to the release notes with its device/emulator
model and Flutter version.

## 4. Consequences for the app (already reflected in the manifest)

1. Hide the vehicle selector (0 vehicles).
2. Hide the Arabic toggle; serve `title_en` only.
3. Hide the procedure section; `v_dtc_tests` is empty.
4. Show the "conflict under review" state for the 503 conflicted codes
   (`v_dtc_conflicts`, status `needs_review`).
5. Render `definition_only` rows as "definition only — no verified diagnosis" rather
   than a diagnostic card.
