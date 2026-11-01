# Execution plan for the production dataset (v1.0.0)

Prepared 2026-11-01 · based on the measured artifacts `0.5.0-rc1` (public and private editions).
Nothing in this plan is an estimate of content: every count below is a query against the built
database, and the workload figures are reviewer-days, not promises.

## 1. Final coverage scope to declare

**Declared supported at v1.0.0** (numbers are the *current* content; each column states what must
still be added before the scope is met):

| Dimension | Today | Target for v1.0.0 | Gap |
| --- | ---: | --- | --- |
| DTC identities (public) | 19,089 | same population, fully defined | 0 (all have an EN definition) |
| — generic | 9,699 | every one diagnosis-ready | **166 generic codes have a definition but no causes/symptoms/repairs** |
| — manufacturer | 9,390 | diagnostic content where a source exists | **9,390 have definition only** — no licence-cleared source provides manufacturer causes |
| Causes / symptoms / repairs | 9,533 / 7,443 / 9,533 identities | ≥ 90 % of generic | ~2,400 generic identities missing symptoms, ~2,330 missing related codes |
| Arabic titles | 0 | 100 % of generic titles reviewed | **19,089 titles + 9,533 descriptions to translate and review** |
| Inspection procedures | 0 | ≥ 20 verified, covering the top generic high-risk codes | **2,028 high-risk identities have no procedure** |
| Vehicles / engines / ECUs (public) | 0 / 0 / 0 | linked by evidence | blocked on the licence decision (private edition already holds 1,538 vehicles, 1,105 ECUs, 24 variants) |
| PIDs (public) | 132 | standard OBD-II complete + names | 132 present; scaling formulas require review |
| Conflicts open (public/private) | 503 / 4,435 | 0 critical unreviewed | **592 critical** (private), 3,843 high, 0 medium, 0 low |

**Not in scope for v1.0.0** (declared, not hidden): UDS DIDs, proprietary manufacturer PIDs,
market-specific statements, and any vehicle relation that no source documents.

## 2. Work remaining, per phase

### Phase B — DTC content (the core of the release)

1. Finish the 166 generic identities that carry a definition but no causes: they are Wal33D-only
   generics. Options: (a) leave them `definition_only` and declare it, (b) obtain a source with
   causes. No third option exists that respects "no invented content".
2. Manufacturer identities (9,390 public): no licence-cleared diagnostic content exists. They stay
   `definition_only` unless a manufacturer source is licensed. This is a *scope* decision, not work.
3. Symptoms/related-code coverage inside OBDex: fixed by upstream, not by us.

**Deliverable:** a per-code completeness report (`v_dtc_search.content_tier`) plus the declared
`definition_only` list published with the release.

### Phase C — Vehicles / engines / ECUs

Blocked on the licence decision for autodiag2 (ODbL) and OBDb (CC-BY-SA). The private edition already
contains 1,538 vehicles, 24 variants, 1,105 ECUs, 1,516 vehicle metadata files and 1,085 ECU records,
with provenance. The moment a decision is recorded, phase C is a **rebuild**, not a re-import:
`--source-set public` already carries the machinery.

Work that can proceed before the decision: define the evidence rule (a DTC↔vehicle link requires a
source that states it), and add the validator (`D012`) that refuses links without a claim.

### Phase D — PIDs

132 PIDs with names; formulas/ranges need verification. OBDb would add ~1,000 signals but is
licence-pending. Work: unit/scale test vectors for the formulas we ship (documented reference cases),
and mark every PID whose scaling is unverified.

### Phase E — Arabic

Infrastructure exists (`translations`, review states, template export, loader that refuses unreviewed
entries). What is missing is human work: **19,089 titles + 9,533 descriptions** at roughly 60-80
short titles per translator-day ≈ **240-320 translator-days** for the generic layer alone, plus review
capacity of at least one independent technical reviewer. The glossary in
[PHASE2_TRANSLATION_PLAN](PHASE2_TRANSLATION_PLAN.md) is the prerequisite for the first batch.

### Phase F — Inspection procedures

Zero content today. Target: **20 verified procedures** for the highest-risk generic codes (P0300-P0304,
P0171, P0172, P0420, P0455, P0128 …), each with author, independent reviewer and a vehicle test.
Workload: 2-4 days per procedure including review and validation ≈ **40-80 technician-days**, plus the
schema work (already specified in [PHASE2_DTC_PROCEDURES_PLAN](PHASE2_DTC_PROCEDURES_PLAN.md)).

### Phase G — Conflicts

Done: `list-conflicts`, `review-conflict`, persisted decisions, and now `triage-conflicts`
([CONFLICT_TRIAGE_REPORT](CONFLICT_TRIAGE_REPORT.md)): 4,435 conflicts → **592 critical, 3,843 high**
(all generic-context; none in manufacturer contexts, because only one source documents those).
Remaining: the decisions themselves. Critical ones first — 592 entries at ~3-6 minutes each ≈
**30-60 reviewer-hours**, plus the 3,843 high ones.

### Phase H — Final public build

After B and G: rebuild, run all gates, regenerate every report from the artifact, freeze the version.

### Phase I — SQLite / Flutter / Android

Done: 13-view contract, portable SQL, `integrity_check`/`foreign_key_check` clean, measured query
cost (exact code 0.01 ms, name scan 10-18 ms), client guide.
Remaining: an Android run on a real device/emulator (not possible in this sandbox — no Flutter SDK, no
emulator, no device), and a cold-start I/O measurement on the target device class.

### Phase J — Release

`v1.0.0` tag only after: declared scope met or formally reduced, licence review closed, quality and
integration tests green, Android test recorded, gaps documented, manifest + SHA-256 published.

## 3. Dependencies and sources

| Need | Source / decision | Blocks |
| --- | --- | --- |
| Vehicle / ECU / engine data | licence decision on autodiag2 (ODbL-1.0) and OBDb (CC-BY-SA-4.0) | phase C, vehicle search, 1,538 vehicles |
| Arabic | named translators + technical reviewer | phase E |
| Procedures | licensed procedure source, or an authoring/review agreement | phase F |
| Conflict decisions | a reviewer with the upstream evidence | phase G critical batch |
| Android verification | device/emulator with the Flutter SDK | phase I completion, phase J |

## 4. What I will do next, in order

1. **Phase B measurement**: per-code completeness table and the `definition_only` list.
2. **Phase G batches**: the 592 critical conflicts exported as review batches (code, both statements,
   sources, similarity), ready for a human to decide in `data/reviews/conflicts.yaml`.
3. **Phase I**: a self-contained Android/Flutter harness (Dart + a script that runs the same contract
   queries) that the owner can execute on a device, since this sandbox cannot.
4. **Phase J preparation**: release checklist, changelog, manifest template — no tag until the
   conditions above are met.

## 5. What cannot be produced by this project, by design

Arabic without a human reviewer, procedures without an author and a reviewer, vehicle links without a
source, and conflict decisions without a decision-maker. The engine will keep reporting those as zero
rather than manufacturing them.
