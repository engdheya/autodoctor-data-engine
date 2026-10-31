# Publication: the public / private split

The engine treats licensing as a **build input**, not as documentation. A build declares a
*source set*; everything downstream — merge, gates, export, bundle, manifest — is derived from it.

```
config/sources.yaml ──► source set ──► staged bundles ──► merge ──► gates ──► artifact
   (licences)          (licence        (only the        (only       (D007 +      (-public suffix)
                        boundary)        allowed ones)    allowed)    D011)
```

## 1. The licence record decides membership

Each source declares, in `config/sources.yaml`:

```yaml
    licence:
      code: ODbL-1.0        # the repository's code licence (we copy no code)
      data: ODbL-1.0        # the licence of the data we redistribute
      redistribution_allowed: true
      share_alike: true
      legal_review: pending # approved | pending | rejected
```

`LicenceInfo.blocking` is true unless the review is `approved` **and** redistribution is not
`false`. A source is in the public set only when it is not blocking.

Current state, as reported by `autodoctor source-set`:

```
source set: private
  include  obdex              CC0-1.0        legal review approved
  include  wal33d             MIT            legal review approved
  include  autodiag           ODbL-1.0       legal review pending
  include  obdb               CC-BY-SA-4.0   legal review pending

source set: public
  include  obdex              CC0-1.0        legal review approved
  include  wal33d             MIT            legal review approved
  EXCLUDE  autodiag           ODbL-1.0       legal review pending
  EXCLUDE  obdb               CC-BY-SA-4.0   legal review pending
```

## 2. Four independent controls

Nothing about this depends on a human remembering to filter:

| Layer | Control | Where |
| --- | --- | --- |
| configuration | `Settings.resolve_source_set(set, requested)` — asking for an excluded source is an **error**, never a silent downgrade | `config.py` |
| build | only the resolved bundles are loaded, merged and counted; excluded sources are listed in the output and in the manifest (`sources_excluded`) | `database/build.py` |
| release gates | `D007_licence_review` becomes **blocking** in a public build, and `D011_public_source_set` fails when any source row, provenance claim or conflict evidence references data outside the licensed set | `validators/database_rules.py` |
| artifact | `build_app_bundle(..., source_set="public")` refuses (`LicenceError`) and deletes the half-written bundle if the file contains an unapproved source | `database/app_export.py` |

The sample-database script (`scripts/build_sample_db.py`) applies the same rule: it refuses to
sample a private database unless you pass `--allow-private`.

## 3. Usage

```bash
# what would each set contain, and why
autodoctor source-set

# internal build: everything, licence gate warns
autodoctor build-db --version 0.4.0 --source-set private
#  -> data/exports/autodoctor-0.4.0.sqlite            (169.5 MB)
#  -> data/exports/autodoctor-app-0.4.0.sqlite        ( 71.2 MB)
#  -> 9/11 gates pass; D007 and D011 are warnings

# publishable build: only CC0 + MIT data
autodoctor build-db --version 0.4.0 --source-set public
#  -> data/exports/autodoctor-0.4.0-public.sqlite     (105.8 MB)
#  -> data/exports/autodoctor-app-0.4.0-public.sqlite ( 52.1 MB)
#  -> 11/11 gates pass

# a public build may still be narrowed further
autodoctor build-db --version 0.4.1 --source-set public --source wal33d

# this fails, by design
autodoctor build-db --source-set public --source autodiag
# configuration error: source set 'public' excludes autodiag (legal review pending, ODbL-1.0)
```

The `-public` suffix is part of the artifact name, so the two builds can never be confused, and
`manifest.source_set` + `db_versions.source_set` record it inside the files themselves.

## 4. What the two builds contain (release 0.4.0, measured)

| | private | public |
| --- | ---: | ---: |
| Sources | 4 | 2 (obdex, wal33d) |
| DTC identities | 40,222 | 19,089 |
| Distinct codes | 19,216 | 12,412 |
| Definitions | 65,108 | 37,871 |
| Verified / conflicting | 14,029 / 8,971 | 16,652 / 1,006 |
| Causes · symptoms · repairs | 28,334 · 26,283 · 9,533 | 28,334 · 26,283 · 9,533 |
| Evidence links | 61,729 | 32,944 |
| PIDs · vehicles · ECUs | 1,541 · 1,538 · 1,105 | 132 · 0 · 0 |
| Conflicts (open) | 4,435 | 503 |
| Provenance claims | 352,761 | 233,432 |
| Release gates passed | 9/11 (two licence warnings) | **11/11** |
| Database / app bundle | 169.5 MB / 71.2 MB | 105.8 MB / 52.1 MB |

Only OBDex supplies causes, symptoms and repairs, so those counts are identical in both builds —
a good illustration of *why* the public build is still a useful product.

## 5. Tests that keep it true

`tests/test_publication.py` (12 tests) asserts, on a fully staged project:

* the sets are derived from the licence record, and `redistribution_allowed: false` on an approved
  source removes it from the public set;
* a private build keeps all four sources and D007/D011 are non-blocking warnings;
* a public build contains **only** approved sources — checked at claim level *and* table level
  (`pids WHERE scope='vehicle'`, `vehicles`, `data_sources`);
* a leaked database (the private build inspected with `source_set="public"`) fails `D011`;
* `build_app_bundle(..., source_set="public")` raises `LicenceError` and leaves no file behind;
* `--source-set public --source autodiag` raises instead of quietly dropping the source;
* the two artifacts have distinct names and the manifest records the set and the exclusions.

`tests/test_sample_db.py` adds the same boundary for the sample database.

## 6. When a legal review closes

1. Edit `config/sources.yaml`: `legal_review: approved` (and `redistribution_allowed: true`).
2. Run `autodoctor source-set` — the source moves into the public set automatically; no code change.
3. Rebuild: `autodoctor build-db --version 0.5.0 --source-set public`. The share-alike obligation is
   still real: see [LICENSES](LICENSES.md), which explains why an ODbL/CC-BY-SA source makes the
   *database* share-alike even when the review is approved.
4. Update `THIRD_PARTY_NOTICES.md` (it is generated from the same registry) and re-run the tests.
