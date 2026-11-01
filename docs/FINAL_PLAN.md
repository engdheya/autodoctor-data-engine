# Final production plan (phases A–J)

This is the plan of record for turning the phase‑1 engine into the commercial dataset. It is
deliberately blunt: the phases are ordered so that nothing is *claimed* before it is *measured*, and
every phase names the input it cannot manufacture.

## The one thing this project will not do

It will not invent diagnostic content. No generated causes, no machine-translated Arabic published
as reviewed, no procedure written from memory, no vehicle compatibility without a source. Where a
phase cannot be completed from real, licence-cleared data, this plan says so and the release
downgrades its claim instead of padding a field.

**That has a direct consequence for scope:** a commercial v1.0.0 can be produced today with certified
DTC coverage and certified licence compliance, but it cannot carry reviewed Arabic, inspection
procedures, or vehicle applicability, because those need a human translator, an authoring/review
process, and a licence decision respectively. The release notes must say exactly that.

## Phases

| Phase | Scope | Status | Blocked by |
| --- | --- | --- | --- |
| **A** | Source and licence audit; declared coverage scope; measured coverage tooling | **done** — `LICENSE_COMPLIANCE_REPORT.md`, `autodoctor coverage` | — |
| **B** | DTC definitions, causes, symptoms, repairs: complete within the declared population | in progress — measured per-field, gaps identified | OBDex is the only source of causes/symptoms/repairs; manufacturer contexts from Wal33D have **no** diagnostic content |
| **C** | Manufacturers / vehicles / engines / ECUs | blocked | the only sources are autodiag2 (ODbL) and OBDb (CC-BY-SA), both licence‑pending |
| **D** | PIDs, scaling formulas, UDS DIDs | partial — 132 PIDs with names; formulas/ranges measured | OBDb PIDs are licence‑pending; no UDS source |
| **E** | Arabic content | blocked | requires a human translator **and** a human reviewer per entry; 0 published today |
| **F** | Inspection procedures | blocked | requires authored + twice-reviewed content; no licensed source ships procedures |
| **G** | Conflict decisions | tooling done, queue open | 4,435 decisions need a reviewer with the upstream evidence in front of them |
| **H** | Final public build | pending (after B/G) | — |
| **I** | SQLite, performance, Flutter/Android verification | partially done — integrity, FK, index, query timings and the query contract are testable here; a real Android run is **not** possible in this sandbox | an Android device/emulator and the Flutter SDK |
| **J** | Final audit + release `v1.0.0` | pending | A–I |

## What v1.0.0 can honestly claim today

* **19,089 DTC identities / 12,412 distinct codes** from two licence-cleared sources, each with an
  English definition and per-fact provenance.
* **9,533 identities (49.9 %)** carry causes, symptoms and repairs — i.e. are *diagnosis-ready*.
  The remaining 9,556 are definitions only, and the app must label them that way.
* **Zero** Arabic, **zero** procedures, **zero** vehicle/ECU links. These are declared unsupported,
  not hidden.
* Licence compliance: the public artifact provably contains nothing from a pending source, and the
  proof is a set of SQL queries against the artifact itself, not a statement of intent.

## What the commission needs from the owner (cannot be engineered)

1. **A licence decision** on ODbL‑1.0 (autodiag2) and CC‑BY‑SA‑4.0 (OBDb). Until then vehicles/ECUs
   cannot ship publicly, and phase C stays blocked. This is the single highest-value decision: it
   unlocks 1,538 vehicles, 1,105 ECUs and 26,409 manufacturer contexts.
2. **Named Arabic translators and reviewers.** The pipeline, gates and glossary exist; the humans do
   not. Machine translation is excluded by design.
3. **A procedure source or an authoring agreement.** 20 verified procedures are the phase‑2 target,
   each with an author, a reviewer and a vehicle test.
4. **A reviewer for the conflict queue** (4,435 entries; 503 already in the public edition).

## Ordering rule

Phases B and G come before H because publishing a build with unresolved *critical* diagnostic
conflicts would be worse than publishing less content. Phase A's tooling exists precisely so that
each later phase can state its numbers instead of its intentions.
