# Data availability audit — what the licensed sources actually contain

Measured 2026-11-02 over the four fetched snapshots (62,154 raw records). Every number
below comes from reading the raw payloads, not from the built database.

## Per source

| Source | Licence | Records | Dimensions present |
| --- | --- | --- | --- |
| OBDex (foerbsnavi) @ `5e927da` | **CC0-1.0** (data) / MIT (code) | 9,665 | 9,533 DTC · 132 PID. Per code: title, description (en+de), `common_causes` with likelihood, symptoms (7,525), repair metadata with difficulty/cost/hours (9,533), flags (MIL, drive cycle, limp mode, emissions), affected components, 6+ reference URLs (`sae:J2012`, TSBs), `reviewed` flag set on 3,142 |
| Wal33D/dtc-database @ `04c43d7` | **MIT** | 18,805 | code + manufacturer + one-line description only. No causes, symptoms, repairs, procedures |
| autodiag2 @ `11e73fd` | **ODbL-1.0 + DbCL-1.0** (contents), GPL-3.0 (code) | 31,434 | 28,833 DTC definitions with evidence URLs, 1,085 ECU records, 1,516 vehicle records |
| OBDb (5 repos) @ `0c57239` | **CC-BY-SA-4.0** | 2,250 | 2,218 PID signal sets, 17 vehicles, 15 ECUs |

## Per dimension — measured, with the honest verdict

| Dimension you asked for | Present in licensed sources | Verdict |
| --- | --- | --- |
| DTC definitions | 12,412 distinct codes / 19,089 identities in the public envelope; 19,216 with ODbL included | **Deliverable** |
| Causes | 28,334 attributed cause statements (OBDex `common_causes`, with likelihood) | **Deliverable** |
| Symptoms | 26,283 (OBDex) | **Deliverable** |
| Repair guidance + difficulty/cost/hours | 9,533 (OBDex) | **Deliverable** |
| Severity / impact on the car | MIL, drive-cycle, limp-mode and emissions flags on 9,533 codes; upstream `reviewed` on 3,142 | **Deliverable** |
| Inspection procedures (steps, tools, nominal values, limits, warnings) | **0 of 62,154 raw records contain a procedure or a measurement value** | **Not available** — needs authored content |
| Arabic | **0 of 62,154 records contain any Arabic**; OBDex ships en + de only | **Not available** — needs authored + reviewed content |
| Vehicles / engines / ECUs | Only in autodiag (ODbL) and OBDb (CC-BY-SA) | **Licence-blocked** for a commercial bundle |
| PIDs | 132 CC0 (OBDex) + 2,218 CC-BY-SA (OBDb) | 132 deliverable commercially |

## Why this matters for the acceptance criteria

Your criteria require procedures with tools/nominal values and reviewed Arabic inside the
database. Neither exists in any source that may be redistributed commercially, and the
project rule (yours) forbids inventing diagnostic content. So those two dimensions cannot
be *sourced*; they can only be *authored and approved*.

The engine therefore does the following, and only the following:

1. Ships every fact the licensed sources really contain, attributed per claim.
2. Produces **drafts** for procedures and Arabic, marked `machine_draft` /
   `unreviewed_draft`, excluded from `diagnosis_ready`, and visible as such in the API.
3. Provides the review workbooks and the import path so a human approval turns a draft
   into reviewed content with one command — and records who approved what.
4. Refuses to publish (gate D012) while a critical conflict is undecided.

Anything beyond that would be fabricated content, which the project rules forbid.
