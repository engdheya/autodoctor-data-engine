# Release status — 0.6.0-rc1 (candidate, not a release)

**Date:** 2026-11-01 · **Version:** `0.6.0-rc1` · **Tag `v1.0.0`:** not created, and will
not be created until the acceptance criteria below pass.

Two artifacts exist, both pinned in their manifests. Neither is client-ready.

| | Public bundle | Internal (private) build |
| --- | --- | --- |
| Force/File | `autodoctor-0.6.0-rc1-public.sqlite` | `autodoctor-0.6.0-rc1.sqlite` |
| Bytes | 105,771,008 | 170,323,968 |
| SHA-256 | `9e43aad48cd908d6fb42bf325a7201757947312f3978edbccf5557110772d66d` | `c286a624f0fa3a90…` (full value in manifest) |
| App bundle | `autodoctor-app-0.6.0-rc1-public.sqlite`, 56,840,192 B, `dd759fe60780722a…` | `autodoctor-app-0.6.0-rc1.sqlite`, 78,151,680 B, `5f60ce2d62864495…` |
| Source set | 2 sources (OBDex CC0-1.0, Wal33D MIT) | 4 sources |
| Codes (distinct) | 12,412 over 19,089 identities | 19,216 |
| Conflicts | 503, all `needs_review` | 4,435, all `needs_review` |
| Vehicles / PIDs | 0 vehicles, 132 PIDs | 1,535 vehicles, 2,528 PIDs |
| Tests / Arabic | 0 / 0 | 0 / 0 |
| DB checks | 12/12 passed | 10/12 (D007, D011 warn — unlicensed sources) |
| **Gate D012** | **overridden** — 18 unreviewed critical conflicts | **overridden** — 592 |

Both manifests carry the override verbatim (`gate_overrides`, `notes`, `warnings`), so no
reader of the artifact can mistake it for a clean pass. The un-overridden build of the
public source set was blocked, as designed:

```
[FAIL] D012_critical_conflicts: 18 unreviewed critical conflict(s);
       first: P20E0, P20E1, P20EF, P2113, P2114
release blocked by failing gates
```

## What is inside the data (measured, from `data/reports/completeness.json`)

Per-identity completeness over 10 tracked facts across the 19,089 public identities:

| Fact | Codes with it |
| --- | --- |
| `definition_en` | 19,089 |
| `description_en` | 9,533 |
| `causes` | 9,533 |
| `symptoms` | 7,443 |
| `repairs` | 9,533 |
| `tests` (procedures) | **0** |
| `related_codes` | 7,203 |
| `risk_level` | 8,594 |
| `mil` | 9,533 |
| `emissions_relevant` | 8,711 |

Totals: 9,533 `diagnosis_ready`, 9,556 `definition_only`, **0 fully complete** — because
no code has an inspection procedure. That is the single largest gap and it is disclosed
per code, not averaged away (`data/reports/completeness.csv`, one row per identity).

## Conflict review (requirement 1–3)

- `autodoctor review-batch --band critical --limit 25 --write` produced
  `data/reviews/batches/private-critical-001.yaml` (25 of 592, internal build) and
  `data/reviews/batches/critical-001.yaml` (18 of 18, public build). Each entry carries
  both statements, source name, licence, repo, commit, similarity, fingerprint, and a
  ready-made `autodoctor review-conflict …` command.
- The generator asserts nothing is decided: a test compares every conflict row before and
  after batch creation. **Triage is not resolution.**
- Decided conflicts are recorded in `data/reviews/conflicts.yaml` and then pass the gate
  without an override (`accepted_difference` is a human judgement, and the D012 test suite
  covers the accepted-difference path).

## Blockers between this candidate and `v1.0.0`

| # | Blocker | Evidence |
| --- | --- | --- |
| 1 | 592 critical conflicts (18 in the public set) undecided | both batch files; gate detail lines |
| 2 | 0 inspection procedures for 19,089 identities | completeness: `tests = 0` |
| 3 | 0 reviewed Arabic rows; 2 example translations are skipped as unreviewed | build warnings |
| 4 | 0 vehicles / 0 ECUs in the public bundle; public vehicle/ECU licences unclosed | manifest counts, D007 |
| 5 | CI workflow not active in the repository | `docs/CI_HANDOFF.md` (App lacks `workflows` permission) |
| 6 | No Android/Flutter on-device run | `docs/ANDROID_FLUTTER_VERIFICATION.md` (SQL contract verified; device run NOT DONE) |

## Reproduce

```bash
pip install -e ".[dev]"
autodoctor fetch-sources && autodoctor import --all
autodoctor build-db --version 0.6.0-rc1 --source-set public      # blocked by D012 (expected)
autodoctor build-db --version 0.6.0-rc1 --source-set private \
    --allow-unreviewed-critical "reason" --override-reviewer "name"
autodoctor review-batch --band critical --limit 25 --batch 1 --write \
    --database data/exports/autodoctor-0.6.0-rc1.sqlite
autodoctor completeness --write --database data/exports/autodoctor-0.6.0-rc1-public.sqlite
python flutter_harness/tool/verify_contract.py \
    --database data/exports/autodoctor-app-0.6.0-rc1-public.sqlite
python -m pytest          # 231 passed, 5 skipped
```
