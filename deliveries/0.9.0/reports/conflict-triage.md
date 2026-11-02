# Conflict triage

Generated: 2026-11-02T15:46:25Z

Triage is an **order of work**, not a decision. Every conflict below is still
`needs_review` and both statements are still shipped; nothing is chosen here. The only
place a judgement is recorded is `data/reviews/conflicts.yaml`.

## Rules

* `critical` - generic code, risk in ['high', 'critical'], similarity < 75%
* `high` - any other generic code
* `medium` - manufacturer/ECU/vehicle context, similarity < 85%
* `low` - manufacturer/ECU/vehicle context, similarity >= 85% (wording variants)

## Counts

| Band | Conflicts |
| --- | ---: |
| critical | 14 |
| high | 379 |
| medium | 0 |
| low | 0 |
| **total** | **393** |

By context: `generic` 393

By risk level of the code: `medium` 193, `unknown` 137, `low` 46, `high` 17

By source pair: `obdex + wal33d` 393

By statement similarity: `0-25%` 37, `25-50%` 141, `50-75%` 112, `75-90%` 103, `90-100%` 0

## critical batch - 14 conflicts

| Code | Context | Similarity | Risk | Sources | Conflict |
| --- | --- | ---: | --- | --- | --- |
| P20E0 | generic | 41% | high | obdex, wal33d | `c6afcd44cb87712c` |
| P20E1 | generic | 35% | high | obdex, wal33d | `6f77b77f3c94f250` |
| P20EF | generic | 33% | high | obdex, wal33d | `ffc30517d65a4529` |
| P22F1 | generic | 34% | high | obdex, wal33d | `9cdc8d2653e1f10e` |
| P2413 | generic | 67% | high | obdex, wal33d | `26dfef8005401b3f` |
| P2458 | generic | 67% | high | obdex, wal33d | `cfd28c677631d6a6` |
| P2460 | generic | 36% | high | obdex, wal33d | `68d330cfafe161cf` |
| P2461 | generic | 35% | high | obdex, wal33d | `ca8fb3c675872c08` |
| P2462 | generic | 53% | high | obdex, wal33d | `c32a52f8da504837` |
| P2BAB | generic | 62% | high | obdex, wal33d | `c1deae54810a7f82` |
| P2BAC | generic | 47% | high | obdex, wal33d | `c18c612e7bd58de0` |
| P2BAD | generic | 52% | high | obdex, wal33d | `1e7e6d1c57fa137b` |
| P2BAE | generic | 67% | high | obdex, wal33d | `7f23389ebc6b46aa` |
| P2BAF | generic | 32% | high | obdex, wal33d | `9ac8bb3729be6b9c` |

_Why this band:_ generic code with risk 'high' whose statements agree only 41%: publishing it unreviewed shows the user a possibly wrong meaning for a safety-relevant fault

## high batch - 379 conflicts

| Code | Context | Similarity | Risk | Sources | Conflict |
| --- | --- | ---: | --- | --- | --- |
| B0003 | generic | 63% | - | obdex, wal33d | `ca9d218b27127b54` |
| B0004 | generic | 50% | - | obdex, wal33d | `952b11f28b2a975f` |
| B0005 | generic | 44% | - | obdex, wal33d | `91cb2b11bbf8b13a` |
| B0010 | generic | 78% | - | obdex, wal33d | `6211ed5e43ece2bc` |
| B0018 | generic | 49% | - | obdex, wal33d | `529de7a06a665875` |
| B0019 | generic | 50% | - | obdex, wal33d | `e0a71d007862e846` |
| B0021 | generic | 72% | - | obdex, wal33d | `59d668aa144cb0a8` |
| B0022 | generic | 56% | - | obdex, wal33d | `b0f3c14a0af5421f` |
| B0028 | generic | 80% | - | obdex, wal33d | `ea472a7e9e5f1b92` |
| B0029 | generic | 81% | - | obdex, wal33d | `3cd57811587e7f6e` |
| B0030 | generic | 45% | - | obdex, wal33d | `0934ab9ac24b66ad` |
| B0031 | generic | 32% | - | obdex, wal33d | `4a265b53ab43ab1c` |
| B0032 | generic | 43% | - | obdex, wal33d | `1800794f16ce1e9f` |
| B0033 | generic | 40% | - | obdex, wal33d | `0b9162d3edb539bd` |
| B0040 | generic | 35% | - | obdex, wal33d | `a5c988e2ce398e3f` |
| … | | | | | 364 more in the JSON |

_Why this band:_ generic code: this is the definition most users will see, so it is reviewed before any manufacturer-specific one

## What publishing an unreviewed conflict does

* the conflict stays in the bundle (`v_dtc_conflicts`) with both statements;
* both statements keep `verification_status = 'conflicting'`;
* the client must show the disagreement, never a single chosen meaning;
* the release notes must quote the open count per band.

