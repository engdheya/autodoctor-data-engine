# Legal review request — commercial distribution of the AutoDoctor AI database

**Prepared by:** the data-engineering side of the project (technical record, not legal advice)
**Date:** 2026-11-01 · **Question deadline:** before the first public release (`v1.0.0`)

## 1. What the product is

AutoDoctor AI is an Android application (Flutter) that explains diagnostic trouble codes (DTCs) and
helps a user decide what to check. The knowledge ships **inside the app as a local SQLite file**; the
app does not call our servers to answer a code lookup.

Two artifacts exist:

| Artifact | Contents | Distributed? |
| --- | --- | --- |
| **Public database** (`autodoctor-*-public.sqlite`, app bundle) | only sources whose licence permits redistribution | **yes**, bundled in the app on Google Play and any other store |
| **Private database** (`autodoctor-*.sqlite`) | all four sources, including the two under review | **no**, internal builds only |

The app is intended to be **paid or free-with-subscription**: commercial use is assumed.

## 2. Sources and their terms (as declared upstream)

| Source | Data licence | Code licence | Attribution | Share-alike | Currently in the public artifact |
| --- | --- | --- | --- | --- | --- |
| OBDex (`foerbsnavi/OBDex`) | CC0-1.0 | MIT | no | no | **yes** |
| Wal33D (`Wal33D/dtc-database`) | MIT | MIT | yes (notice) | no | **yes** |
| autodiag2 (`autodiag2/database`) | **ODbL-1.0** (database) + DbCL-1.0 (contents) | GPL-3.0-or-later | yes | **yes** | no — pending |
| OBDb (org, 5 vehicle repos) | **CC-BY-SA-4.0** | — | yes | **yes** | no — pending |

Facts that matter for the analysis, measured:

* autodiag2 contributes 31,433 records (~28,832 DTC definitions, 1,085 ECU records, 1,516 vehicle
  metadata files) and states that 27,967 of its files cite `obdcodex` as their source — i.e. it is
  largely a re-publication of a third party.
* OBDb contributes no DTC definitions; it contributes vehicle signal sets (`signalsets/v3`), ECU
  headers and PIDs (1,051–2,503 signals depending on the org's current repositories).
* OBDex is CC0 and OBDex-only content (causes, symptoms, repairs, risk flags for generic codes) is
  what the current public artifact is built on, together with Wal33D's manufacturer definitions.

## 3. What we do to the data (relevant to "derivative database")

1. Parse each source into our own schema (no verbatim file redistribution of the raw sources).
2. Normalise text, unify manufacturer names, split languages.
3. Merge exact duplicates into one row with several provenance claims; keep differing statements apart.
4. Compute *derived* fields: risk level from MIL/emissions/limp flags (`risk_flags_v1`), verification
   status from lineage counting.
5. Ship per-fact provenance: source, commit, licence, retrieval date, verification status.

We do **not** copy source files verbatim into the app; the app contains a database of facts extracted
from them, plus our derived judgements.

## 4. The specific questions

1. **ODbL-1.0 (autodiag2).** If we include facts from autodiag2 in the app's database, is the app's
   database a "derivative database" that must be offered under ODbL (§4.4)? What does "publicly
   distributed" mean for a file bundled in a paid Android app? Would offering the database file (or
   the extraction) under ODbL satisfy the licence while keeping the *application* proprietary? What
   attribution notice ("§4.3") would be required in-app, and does the DbCL-1.0 grant on contents change
   the analysis of the individual definitions?
2. **CC-BY-SA-4.0 (OBDb).** The same question for the vehicle signal metadata: is a merged database
   containing those rows an "adaptation"? Can the adaptation be inside a proprietary app if the
   database itself is offered under CC-BY-SA? Does merely *linking* DTCs to the vehicles OBDb
   describes change the answer?
3. **Combination.** If both were approved, can one database satisfy ODbL *and* CC-BY-SA at the same
   time (dual licensing of the database artifact), and what does that imply for the app's own
   derivative fields (risk levels, our Arabic text)?
4. **Our own contributions.** Arabic translations, derived risk levels and our schema: can they be
   licensed under different terms than the merged database, or do they inherit share-alike?
5. **Attribution.** What must be visible in-app (about screen, per-fact display) for MIT (Wal33D),
   ODbL and CC-BY-SA, and is a single "Data sources" screen sufficient?

## 5. Options we are considering (engineering consequences noted)

| Option | Upside | Consequence |
| --- | --- | --- |
| **A. OBDex + Wal33D only** (current) | clean, no share-alike | no vehicles/ECUs, 19,089 identities, definitions+causes for 9,533 |
| **B. Add autodiag2 with ODbL compliance** | 1,538 vehicles, 1,105 ECUs, ~28k more definitions | our database artifact must be published under ODbL; needs a place to offer it; must attribute odbcodex lineage |
| **C. Add OBDb with CC-BY-SA compliance** | ~1,000 vehicle signals, real ECU headers | adaptation share-alike; attribution required |
| **D. Licence a commercial DTC/vehicle dataset** | clean provenance, manufacturer-level detail | cost, and integration work is already generic |

Engineering is ready for B/C/D: `--source-set` already separates what may ship, and flipping a source
to `legal_review: approved` in `config/sources.yaml` rebuilds the public artifact with the licence
gates (`D007`, `D011`, `assert_public_safe`) re-verified — no re-import needed.

## 6. What we need back

A short written opinion answering §4, one line per source: *may it ship in a commercial app, under
which conditions, with which notice, and what must we publish alongside it*. That answer becomes a
recorded decision in `config/sources.yaml` (`legal_review: approved|rejected`, plus the note), and the
build gates enforce it from then on.
