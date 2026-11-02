# Build log

Every artifact with the hashes taken from its own manifest. Files live in `data/exports/`
(untracked); the public package is also copied to `deliveries/0.9.0/` so it can be downloaded
and checked.

| Version | Source set | DB bytes | DB SHA-256 | App bundle bytes | App bundle SHA-256 | Codes / identities | D012 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.9.0 | **public (commercial)** | 106,221,568 | `d6bc01dff4d527a344c245cb5c8ea36ce2d7274889077df7ac330c2f273084f9` | 57,106,432 | `23b4032d84439d0f0f03ccea8b57079f54f8d0698299e308657a6a28e3e841cf` | 12,412 / 19,089 | 14 undecided critical — not publishable, gate overridden |
| 0.9.0 | private (internal, held back) | 170,885,120 | `72c45ea34c513a924186e7ffb0780c72e0e5a5e9115a8f5160d0acdcadfd54e8` | 78,430,208 | `14d3b8c2e965190bba1f1bfb592df0e17317fea6bd40a5b826c3ec2e559810af` | 19,216 / 40,222 | 588 undecided critical — never distributed, gate overridden |

## 0.9.0 — 2026-11-02

```bash
autodoctor fetch-sources && autodoctor import --all

# commercial candidate: permitted sources only (OBDex CC0-1.0, Wal33D MIT)
autodoctor build-db --version 0.9.0 --source-set public \
    --allow-unreviewed-critical "public-source artifact for client verification only; NOT for publication while critical conflicts are undecided" \
    --override-reviewer "data-engineering"

# internal build: adds ODbL and CC-BY-SA sources, must never be distributed
autodoctor build-db --version 0.9.0 --source-set private \
    --allow-unreviewed-critical "internal build for engineering and review; must never be distributed" \
    --override-reviewer "data-engineering"
```

| | Public (commercial candidate) | Internal |
| --- | --- | --- |
| Codes / identities | 12,412 / 19,089 | 19,216 / 40,222 |
| Causes / symptoms / repairs | 28,426 / 26,437 / 9,533 | 28,426 / 26,437 / 9,533 |
| Vehicles / ECUs / PIDs | 0 / 0 / 132 | 1,532 / 1,099 / 2,694 |
| Conflicts (open) | 393 (393) | 4,329 (4,329) |
| Critical, undecided | 14 | 588 |
| Database checks passed | 12/12 | 10/12 |
| Arabic reviewed / procedures | 0 / 0 | 0 / 0 |
| Distribution | not publishable until the 14 conflicts are decided | none, licence-encumbered (ODbL, CC-BY-SA) |

D011 is clean in the public build (0 facts from unlicensed sources) and fails by design in the
internal build, which is exactly the separation that was asked for.

## Packages

- `deliveries/0.9.0/` — downloadable verification package for the **public** build: 15 files,
  ~66 MB, with `SHA256SUMS` and `verify_delivery.py`. Produced by
  `python scripts/package_delivery.py --version 0.9.0`.
- The internal build is **not** packaged and **not** distributed; only its hashes appear above.
