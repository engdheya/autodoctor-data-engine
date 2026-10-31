# Licences

Two different things are licensed and they must not be confused:

1. **The engine** (this repository's code) — MIT, see [`LICENSE`](../LICENSE).
2. **The data** that the engine merges — governed by the licence of *each* upstream project.

The merged SQLite file is a **derivative database**. Its licence is the union of the obligations
below; it is not MIT and it cannot be relicensed by this project.

## Register

| Source | Code licence | Data licence | Attribution | Share-alike | Commercial | Legal review |
| --- | --- | --- | --- | --- | --- | --- |
| OBDex | MIT | **CC0-1.0** | not required | no | yes | **approved** |
| Wal33D dtc-database | MIT | **MIT** (data in the repository) | required | no | yes | **approved** |
| autodiag2/database | GPL-3.0-or-later | **ODbL-1.0** (database) / **DbCL-1.0** (contents) | required | **yes** | yes, with conditions | **pending** |
| OBDb | MIT-style per repository | **CC-BY-SA-4.0** | required | **yes** | yes, with conditions | **pending** |
| local translations | — | CC-BY-SA-4.0 (deliberate choice, see below) | required | yes | yes | approved |

The register lives in [`config/sources.yaml`](../config/sources.yaml) and is copied into
`data_sources` in every build, so a shipped database always states its own licence conditions.

## What each obligation means in practice

### OBDex — CC0-1.0
The data is dedicated to the public domain. No attribution is legally required; the engine still
records it (good practice, and it keeps the provenance chain complete). Titles, descriptions,
causes, symptoms, repairs and flags from OBDex can be shipped in any product without conditions.

### Wal33D — MIT
The repository is MIT-licensed including its data. Obligation: keep the copyright notice and the
licence text with any substantial portion of the data. This project discharges it by (a) embedding
`data_sources.notes` with the notice, (b) listing the project here, and (c) shipping
`THIRD_PARTY_NOTICES.md` in any release bundle. No share-alike.

### autodiag2 — ODbL-1.0 + DbCL-1.0 (**pending**)
ODbL applies to the *database*: you may use and redistribute it, and any **derivative database**
you publicly distribute must be offered under ODbL as well (share-alike), with attribution and
"keep open" obligations for the database, not for your application code. DbCL applies to the
*contents*: individual facts may be extracted and used, but a substantial extraction keeps
attribution requirements. The repository's code is GPL-3.0-or-later — relevant only if we copy
their code (we do not: the connector is an independent parser of their data files).

Consequence: **a public release that contains autodiag2 rows must be published under ODbL terms for
the database.** Marked `pending` until a human confirms this reading, and until we decide whether
the public bundle ships autodiag2 at all.

### OBDb — CC-BY-SA-4.0 (**pending**)
Attribution required, share-alike applies to adaptations. We do not import DTC text from OBDb (it
has none), only vehicle generations, ECU headers and parameter definitions. Even so, a public
bundle that includes those rows is an adaptation and must carry the same licence plus attribution.

### Local translations — CC-BY-SA-4.0
Arabic and any future human translations are contributions. Being explicit that they inherit the
project's share-alike choice avoids a mixed-licence database later.

## Redistribution strategy

Three artifacts, three audiences:

| Artifact | Contains | Licence position |
| --- | --- | --- |
| engineering DB (`autodoctor-<v>.sqlite`) | everything, plus full provenance | internal / private use; not for public distribution while any source is `pending` |
| app bundle, private build (`--source-set private`) | all sources | personal/company distribution only |
| app bundle, public build (`--source-set public`) | only `redistribution_allowed = 1 AND legal_review_status = 'approved'` sources → **OBDex + Wal33D** | CC0 + MIT: safe to publish, attribution kept |

Gate `D007_licence_review` reports the current state on every build. It is a **warning** today,
because nothing in this repository is public yet; the plan is to make it **blocking** for the
public bundle once the source-set filter lands (see [DEVELOPMENT_PLAN](DEVELOPMENT_PLAN.md)).

## Attribution text to ship

```
AutoDoctor AI diagnostic database.
Contains data from:
  • OBDex (github.com/foerbsnavi/OBDex) — CC0-1.0
  • Wal33D dtc-database (github.com/Wal33D/dtc-database) — MIT
  • autodiag2/database (github.com/autodiag2/database) — ODbL-1.0 / DbCL-1.0
  • OBDb (github.com/OBDb) — CC-BY-SA-4.0, per vehicle repository
Source commits and per-file hashes are recorded in the release manifest.
```

## Rules for contributors

1. Never add a source without a licence entry and a legal review status.
2. Never copy code from a GPL source repository into this one; write an independent parser over the
   data files.
3. Never upload `db/`, `data/exports/`, `data/raw/` or `data/staging/` to a public host before the
   pending reviews are closed. `.gitignore` already excludes them.
4. A source with an unclear licence is excluded from the distributable build and flagged, never
   "assumed permissive".
5. When a licence says share-alike, the *database* carries it — application code does not.
