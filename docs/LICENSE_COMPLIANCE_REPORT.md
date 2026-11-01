# Licence compliance report

**Release candidate `0.5.0-rc1` · public edition · generated 2026-11-01**

> This document records *what each upstream declares*, *what the engine reads*, and *what the build
> therefore contains*. It is an engineering compliance record, not legal advice: the decision to
> publish a commercial client remains the repository owner's, and any source marked **pending**
> below stays out of the public build until that decision is recorded.

## 1. Sources in the registry

| Field | OBDex | Wal33D | autodiag2 | OBDb |
| --- | --- | --- | --- | --- |
| Repository | `foerbsnavi/OBDex` | `Wal33D/dtc-database` | `autodiag2/database` | `OBDb` (org, 5 repos) |
| URL | https://github.com/foerbsnavi/OBDex | https://github.com/Wal33D/dtc-database | https://github.com/autodiag2/database | https://github.com/OBDb |
| Code licence | MIT (`LICENSE-CODE`) | MIT (`LICENSE`) | GPL-3.0-or-later | — (data repos) |
| Data licence | **CC0-1.0** (`LICENSE-DATA`) | **MIT** (`LICENSE`) | **ODbL-1.0** + DbCL-1.0 for contents | **CC-BY-SA-4.0** (`LICENSE`) |
| Licence file | present, 709 B (+1,238 B code) | present, 1,078 B | present, 1,536 B | present in all 5 repos |
| Attribution required | no | **yes** (MIT notice) | **yes** (ODbL attribution) | **yes** (CC-BY) |
| Share-alike | no | no | **yes** (ODbL §4.4) | **yes** (CC-BY-SA §3.b) |
| Commercial use | allowed | allowed | allowed *with* share-alike | allowed *with* share-alike |
| Redistribution | allowed | allowed | allowed *with* share-alike | allowed *with* share-alike |
| Modification | allowed | allowed | allowed *with* share-alike | allowed *with* share-alike |
| Commit imported | `a9d0220bdb99` | `04c43d72e7db` | `11e73fd6d105` | `obdb:b91d26ed09` |
| Imported at (UTC) | 2026-11-01T17:25:32Z | 2026-11-01T17:26:03Z | 2026-11-01T17:26:06Z | 2026-11-01T17:26:34Z |
| Dataset hash | `cfea4a46fb30…` | `78eba04e75e1…` | `a6b654676ea7…` | `cdf5d95442a6…` |
| Legal review | **approved** | **approved** | **pending** | **pending** |
| In the public edition | **yes** | **yes** | no | no |

Dataset hashes are computed by the staging layer over the imported files, so a changed upstream
commit produces a different hash even when the record count is identical.

## 2. What the public production edition contains

```
data/exports/autodoctor-0.5.0-rc1-public.sqlite        105,771,008 bytes
sha256 4faee8dbddbd1cb9cec036b2df3e579954ba26911df99446e3e2e094c61045b2
data/exports/autodoctor-app-0.5.0-rc1-public.sqlite     52,064,256 bytes
sha256 39a7a3643fe502c1d6702c4ac83064b6fa9bcabfb65db8632d1c4eb64a206e4f
```

Verified with direct queries against the artifact (not against the staging area):

```sql
-- every source row in the public database
SELECT slug, data_license, legal_review_status FROM data_sources;
--   obdex   CC0-1.0  approved
--   wal33d  MIT      approved

-- every claim, by source: nothing from autodiag2 or OBDb exists
SELECT s.slug, COUNT(*) FROM provenance_claims p
JOIN data_sources s ON s.id = p.source_id GROUP BY 1;
--   obdex  177,017
--   wal33d  56,415
```

| Control | Mechanism | Result |
| --- | --- | --- |
| Source selection | `--source-set public` filters before the merge | `sources_excluded` records both pending sources in the manifest |
| Merge gate | `D011_public_source_set` counts facts and conflict-evidence rows outside the licensed set | 0 unlicensed sources, 0 facts, 0 evidence rows |
| Licence gate | `D007_licence_review` reports sources that are redistributable but unreviewed | passes in the public build |
| Artifact assertion | `assert_public_safe()` re-reads the finished bundle | refuses to publish on any offender |
| Post-build verification | `_verify_views()` + manifest `sha256` | artifact hash equals the manifest |

## 3. How attribution is satisfied

* **Wal33D (MIT)** — the copyright notice and permission text are reproduced in
  `THIRD_PARTY_NOTICES.md`, which ships with the release; `data_sources.attribution_required = 1`
  and the app's "about the data" screen reads `data_sources` + `data_versions` directly, so the
  notice cannot drift from the database.
* **OBDex (CC0-1.0)** — no obligation; attribution is kept anyway for traceability.
* Per-fact provenance survives into the bundle (`provenance_summary`), so any single statement can be
  traced to the repository, commit, file and record that produced it.

## 4. Sources excluded from the public edition, and why

| Source | Licence | Why excluded | What would unblock it |
| --- | --- | --- | --- |
| autodiag2/database | ODbL-1.0 (data) + DbCL-1.0 (contents), GPL-3.0-or-later (code) | ODbL is share-alike: a *derivative database* distributed publicly must be offered under ODbL, and the app's bundled database is such a distribution. That is a business decision, not an engineering one, and it must be taken before any of its facts ship. | A recorded legal decision accepting ODbL for the distributed database (or a written permission), then `legal_review: approved` in `config/sources.yaml`. |
| OBDb (org) | CC-BY-SA-4.0 | Same class of obligation (attribution + share-alike) and its content is vehicle signal sets, not DTC definitions. | As above, plus a product decision on shipping vehicle-level parameters. |

Neither source is deleted or lost: both are imported, staged, hashed and available in the **private**
edition (`--source-set private`), which is never published. Keeping them there is what allows a
future decision to be executed without re-importing anything.

Engineering consequence to state plainly: because these two are the only sources that provide
**vehicles, ECUs and vehicle-level signals**, the public edition ships **no vehicle or ECU
applicability**. That is a scope consequence of the licence boundary, documented in
`DATA_COVERAGE_REPORT.md`, not an oversight.

## 5. Facts about the upstream data that affect licensing claims

1. **autodiag2 is mostly a re-publication.** 27,967 of its files cite `obdcodex` as their evidence.
   Treating its statements as independent corroboration would be wrong (the engine counts lineages,
   not repositories) and bundling it would impose ODbL on a database whose content is largely
   someone else's.
2. **OBDb contains no DTC definitions.** 0 definitions across the 5 repositories in this run; it
   contributes PIDs and ECU signal sets only.
3. **OBDex is explicitly generic.** It ships SAE J2012 / ISO 15031-6 codes and says so; manufacturer
   contexts come from Wal33D.
4. **Wal33D ships a compiled SQLite database plus the text lists it was built from**, and the two do
   not fully agree (18,805 rows vs 18,826 parseable lines). The compiled database is imported because
   it is the structured artifact; the discrepancy is recorded in `data/reports/source-inspection.md`.

## 6. Repeating the audit

```bash
autodoctor fetch-sources
autodoctor inspect-sources                       # commits, licences, layout, warnings
autodoctor source-set --set public               # who may enter the public build, and why not
autodoctor build-db --version <v> --source-set public
autodoctor coverage --write                      # measured content + scope
```

The numbers in this report come from the artifacts above; if a source moves, the hash, the commit and
the record counts change, and this document must be regenerated rather than edited.
