# Integration results against the real upstream repositories

This is the record of the integration runs, not of the fixture suite. The fixtures prove the logic;
these runs prove the connectors still match reality.

## Environment

| | |
| --- | --- |
| Date | 2026-11-01 |
| Python | 3.11.2 (Linux x86-64), pytest 9.2.0 |
| Command | `AUTODOCTOR_INTEGRATION=1 python -m pytest tests/test_integration_real_sources.py -v` |
| Checkouts | `autodoctor fetch-sources` → `vendor/upstream/{OBDex,dtc-database,autodiag2-database,OBDb}` |
| Total wall time | 48.71 s (`real 0m48.878s`) |

## Result

```console
$ AUTODOCTOR_INTEGRATION=1 python -m pytest tests/test_integration_real_sources.py -v
============================= test session starts ==============================
platform linux -- Python 3.11.2, pytest-9.2.0, pluggy-1.7.0
rootdir: /home/user/autodoctor-data-engine
configfile: pyproject.toml
collected 5 items

tests/test_integration_real_sources.py .....                             [100%]

============================== 5 passed in 48.71s ==============================
```

Without the variable the same five tests are skipped: `205 passed, 5 skipped in 2.35s` for the whole
suite.

## What each test asserts (and what it measured)

| Test | Assertion | Measured on this run |
| --- | --- | --- |
| `test_obdex_real_layout` | the YAML families parse to > 9,000 DTC entries and a normalized record carries definitions | 9,533 entries; 13 keys; the first record normalizes to a `NormalizedDtc` with definitions |
| `test_wal33d_real_sqlite` | > 18,000 rows, > 12,000 unique codes, > 30 manufacturer labels in `dtc_definitions` | 18,805 rows · 12,128 codes · 34 manufacturers (9,415 generic / 9,390 manufacturer rows) |
| `test_autodiag_real_tree` | > 28,000 code files and > 16,000 unique codes under `data-src/**/codes/*.yml` | 28,833 files · 16,674 codes · 1,516 vehicle metadata files · 1,149 ECU definitions |
| `test_obdb_real_repositories` | the org contributes **no** DTC definitions but does contribute signals | 5 repositories · 1,409 signals · 19 ECU entries · **0** DTC definitions, 0 repos with DTC paths |
| `test_public_source_set_on_the_real_registry` | the licence boundary resolves correctly for the real registry, and every source declares both licences | public = `["obdex", "wal33d"]`; excluded = `autodiag` (ODbL-1.0, pending), `obdb` (CC-BY-SA-4.0, pending) |

## Full pipeline on the same checkouts

The integration tests are deliberately bounded (they do not build a 170 MB database on every CI run).
The end-to-end run below was executed once, by hand, on the same commits:

Read from `data/staging/<slug>/<commit>/manifest.json` and the release manifests:

| Source | Raw | Normalized | Rejected | Validation (failed / errors) | Import time |
| --- | ---: | ---: | ---: | --- | ---: |
| obdex | 9,665 | 9,665 (9,533 dtc + 132 pid) | 0 | 25 / 0 | 32.42 s |
| wal33d | 18,805 | 18,805 dtc | 0 | 64 / 0 | 3.30 s |
| autodiag | 31,434 | 31,434 (28,833 dtc + 1,085 ecu + 1,516 vehicle) | **1** (`P15O9`) | 5 / 1 | 29.46 s |
| obdb | 1,447 | 1,447 (1,409 pid + 19 vehicle + 19 ecu) | 0 | 0 / 0 | 0.17 s |

```console
$ autodoctor build-db --version 0.4.0 --source-set public
release checks: 11/11 passed

$ autodoctor build-db --version 0.4.0 --source-set private
release checks: 9/11 passed   (D007 + D011 warn: autodiag and obdb are pending review)
```

| | private | public |
| --- | ---: | ---: |
| DTC identities | 40,222 | 19,089 |
| Distinct codes | 19,216 | 12,412 |
| Definitions | 65,108 | 37,871 |
| Conflicts | 4,435 | 503 |
| Evidence links | 61,729 | 32,944 |
| Claims | 352,761 | 233,432 |

## Observations that came out of running against real data

1. **OBDex `sources` are strings, not objects.** The connector handles both shapes; 23,364 URLs are
   imported as `dtc_evidence_sources` rows.
2. **Wal33D's compiled database contradicts the text lists it ships** (18,805 rows vs 18,826
   parseable lines). Reported by `inspect-sources`; the compiled database is imported because it is
   the richer, structured artifact.
3. **autodiag2 publishes far less than its schema allows** (7 populated keys), and 1,516 vehicle
   `def.yml` files exist but only a fraction declare a complete vehicle.
4. **OBDb has no DTCs.** Confirmed again: 0 definitions, 1,409 signals across 5 repositories.
5. **`P15O9` is still invalid upstream** and still quarantined.

## Reproducing

```bash
autodoctor fetch-sources
AUTODOCTOR_INTEGRATION=1 python -m pytest tests/test_integration_real_sources.py -v
```

CI runs the hermetic suite only; the weekly `upstream-drift` workflow runs `inspect-sources` plus a
bounded import against the live repositories. If an upstream repo changes shape, this file's numbers
are the baseline to compare against.
