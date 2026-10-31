# Phase 2 plan — DTC inspection procedures

**Current state: `dtc_tests = 0`.** No source supplies an inspection procedure, and the engine will
not invent one. This plan defines where procedures come from, how they are stored, and what a
mechanic is allowed to see.

## Why this is a separate dataset, not a text field

A procedure is a sequence of measurements with expected values and a decision at each step. It is not
"check the coil". It must be versioned, attributable, and safe: a wrong step ("back-probe pin 2 with
the ignition on") damages parts. So a procedure is stored as structured steps, each with its own
provenance and trust level, and the UI can only render a procedure whose steps are all verified.

## Data model (additive, schema v4)

```sql
CREATE TABLE dtc_procedures (
  id INTEGER PRIMARY KEY,
  code_id INTEGER NOT NULL REFERENCES dtc_codes(id),
  context_key TEXT NOT NULL,
  title TEXT NOT NULL,
  difficulty TEXT,                 -- easy | moderate | advanced | professional
  tool_requirements TEXT,          -- JSON array
  safety_notes TEXT,
  language TEXT NOT NULL DEFAULT 'en',
  is_translated INTEGER DEFAULT 0,
  translation_reviewed INTEGER DEFAULT 0,
  procedure_status TEXT NOT NULL    -- draft | technical_review | verified | deprecated
);

CREATE TABLE dtc_procedure_steps (
  id INTEGER PRIMARY KEY,
  procedure_id INTEGER NOT NULL REFERENCES dtc_procedures(id),
  step_no INTEGER NOT NULL,
  action TEXT NOT NULL,            -- what to do
  expected TEXT,                   -- what a good result looks like
  on_pass_next INTEGER,            -- next step_no, NULL = done
  on_fail_next INTEGER,            -- branch to a diagnosis, NULL = stop
  measurement_json TEXT,           -- {unit, min, max} when the step is a measurement
  caution TEXT,
  UNIQUE (procedure_id, step_no)
);
```

Steps form a small decision tree, not a flat list: `on_fail_next` is what makes a procedure useful
("misfire on cylinder 1 → swap coil to cylinder 2 → misfire moved? → coil, else plug/wiring").
`explain_code` gains a `procedures` array grouped by `procedure_status`, and the app shows
`verified` ones by default.

## Sources, in order of preference

1. **Licensed aftermarket / OEM service data, bought with an explicit redistribution right.** This is
   the only source that can ever be `verified`.
2. **Public safety recalls** (NHTSA-style, CC0 in some jurisdictions) — usable for safety notes, not
   for complete procedures.
3. **Internal authoring by a qualified technician**, reviewed by a second one; licence `LOCAL`.
4. **Community contributions** — draft only, `technical_review` never skipped, never redistributable
   until the contributor signs a licence.

Nothing scraped, nothing from a forum, nothing paraphrased from a paid manual.
OBDex's `causes` and `symptoms` are *inputs* to authoring, not procedures.

## Authoring and review workflow

```
authoring (internal tool or YAML) → schema validation → technical review (2nd technician)
      → bench/vehicle validation on a real fault → status = verified → release
```

YAML shape mirrors the tables:

```yaml
- code: P0301
  context_key: P0301|sae_j2012|generic:generic
  title: Cylinder 1 misfire — ignition circuit isolation
  difficulty: easy
  tools: [scan tool, spark tester, multimeter]
  steps:
    - no: 1
      action: Read freeze frame with the engine warm; record RPM, load and fuel trims.
      expected: Misfire counter increments at idle.
      on_pass_next: 2
    - no: 2
      action: Swap the ignition coil of cylinder 1 with cylinder 2.
      expected: Misfire follows the coil.
      on_pass_next: 3
      on_fail_next: 4
    ...
```

## Validation gates (new)

| Gate | Rule |
| --- | --- |
| `D012` | a `verified` procedure must have ≥ 3 steps, a tool list and a safety note |
| `D013` | every `on_pass_next` / `on_fail_next` must reference an existing `step_no` in the same procedure; no cycles that never terminate |
| `D014` | a procedure may only attach to a `generic` context of a code that exists; manufacturer procedures need the manufacturer context |
| `D015` | a procedure in `ar` requires `translation_reviewed = 1` and a reviewer ≠ translator (same rule as definitions) |

## Bounded first scope (what phase 2 actually ships)

Do **not** attempt 19,216 codes. Ship a small, honest, fully verified set:

* **the top 20 generic codes with `risk_level = high` and `mil = 1`** (P0300-P0304, P0171, P0172,
  P0420, P0455, P0128, …), one procedure each, authored internally and reviewed twice;
* plus a `procedure_status = 'draft'` skeleton for the rest of the OBDex `causes` layer, so the UI can
  show "what to check" without pretending it is a procedure.

Success criterion for the phase: **20 verified procedures, 0 unverified ones in the app bundle**, each
traceable to an author, a reviewer and a vehicle test.

## What the UI may show

| `procedure_status` | App |
| --- | --- |
| `verified` | full tree, expected values, safety notes |
| `technical_review` | steps visible, marked "review pending", no expected values |
| `draft` | not shown; only the general cause list is shown |
| `deprecated` | hidden, kept for audit |

The app bundle builder gets a `procedures` shrink rule: only `verified` procedures for the requested
language, with steps, plus the `safety_notes` always.

## Licensing note that constrains this

A purchased OEM procedure is usually **not** redistributable. If such data is imported at all it goes
to the **private** database with `redistribution_allowed = 0`, and the public build excludes it
automatically (`assert_public_safe`, `D007`) — the publication rule already covers this case without
new code.
