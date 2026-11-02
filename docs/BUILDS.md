# Build log

Every published artifact, with the hashes taken from its own manifest. The files live in
`data/exports/` (not tracked by git; rebuild with the command shown).

| Version | Source set | DB bytes | DB SHA-256 | App bundle bytes | App bundle SHA-256 | Codes / identities | D012 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.9.0 | private | 170,606,592 | `fffab51e35eab9f31d6ba14ce69048f17c42011e1f30426a3b23d799598fc275` | 78,311,424 | `f0e6562d7b98be8967402f2bbf2e12878b205f092964e671dfb40e1ba921ac23` | 19,216 / 40,222 | overridden, 588 undecided critical |

## 0.9.0 — 2026-11-02

```bash
autodoctor fetch-sources && autodoctor import --all
autodoctor build-db --version 0.9.0 --source-set private \
    --allow-unreviewed-critical "pre-release build while the 592 critical conflicts await human decisions" \
    --override-reviewer "data-engineering"
```

- Vehicles 1,537 · ECUs 1,101 · PIDs 2,350 (vehicles/ECUs come from ODbL and CC-BY-SA
  sources, so this build is **internal only**).
- Conflicts 4,329 open, 588 of them critical and undecided → gate D012 overridden and
  recorded in `gate_overrides` of the manifest.
- 10 of 12 database checks passed; D007 (licence review) and D011 (public source set)
  fail by design on the internal set.
- Arabic: 0 reviewed; the two example translations are skipped as unreviewed.
- Procedures: 0.
