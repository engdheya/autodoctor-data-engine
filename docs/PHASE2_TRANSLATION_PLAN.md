# Phase 2 plan — reviewed human Arabic content

**Current state: 0 Arabic definitions.** No upstream source contains Arabic, and the engine refuses
to machine-translate. Everything below is about producing Arabic content that a reviewer has signed
off, with the provenance to prove it.

## Why not translate automatically

A DTC statement is a safety and money decision: "cylinder 1 misfire" leads to a coil, a plug, an
injector or an engine teardown. A machine translation that shifts a nuance ("circuit high" vs
"signal high") is worse than no translation, and it cannot be audited. The database therefore treats
Arabic exactly like a source: it arrives with a translator, a reviewer, a date and a licence.

## Pipeline that already exists

```
autodoctor export-translation-template      CSV of generic codes with no Arabic yet
        │
        ▼  data/reports/translation-template-ar.csv
translator fills title_ar (+ optional description_ar)
        │
        ▼  data/translations/ar/<batch>.yaml   (format: see the example file)
reviewer sets reviewed: true and names themselves
        │
        ▼  autodoctor build-db
dtc_definitions(language='ar', is_translated=1, translation_reviewed=1)
+ translations(translator, reviewer, source_url)
+ provenance_claims(extraction_method='human_translation', is_derived=1, is_translated=1)
```

Anything without `reviewed: true` **and** a named reviewer is skipped and reported by the build — it
never reaches the database silently. Two entries in `data/translations/ar/example.yaml` demonstrate
exactly that (they appear as `! … translation is not reviewed yet, skipped` in the build output).

## Work plan

### Batch 0 — glossary (1 week, blocks everything else)

A single terminology sheet, agreed once, translated consistently:

| English | Arabic (proposal) | Note |
| --- | --- | --- |
| Diagnostic Trouble Code (DTC) | كود عطل التشخيص | keep "DTC" in Latin on first use |
| Malfunction Indicator Lamp (MIL) | لمبة أعطال المحرك | never "check engine" literally |
| misfire | عدم احتراق | not "اشتعال خاطئ" |
| circuit high / low | دائرة عالية / منخفضة | voltage sense, not "مرتفعة" |
| open circuit | دائرة مفتوحة | |
| short to ground | قصر مع الأرضي | |
| bank 1 / bank 2 | الصف الأول / الصف الثاني | |
| sensor 1 / sensor 2 | الحساس الأول / الثاني | |
| catalyst efficiency | كفاءة الحفاز | |
| evaporative emission (EVAP) | نظام تبخير الوقود | |
| freeze frame | بيانات لحظة العطل | |
| drive cycle | دورة قيادة | |

Rule: keep equipment abbreviations (ECU, PCM, B1S1, DPF, EGR) in Latin script, with the Arabic term
in parentheses on first use in a screen. Do not translate brand names.

### Batch 1 — the generic layer, MIL-relevant first (highest value)

Priority order, all queried from the build:

1. codes with `risk_level IN ('high','critical')` and `mil = 1` (2,028 identities today);
2. codes with causes/repairs (9,533 — every OBDex generic code);
3. the rest of the generic layer (12,947 identities over 9,699 codes in the public build).

Deliverable per batch: `data/translations/ar/generic-<nnn>.yaml`, 200 codes per file (reviewable in
one sitting), with `translator`, `reviewer`, `reviewed: true`.

### Batch 2 — manufacturer layer, on demand

26,409 manufacturer identities. Translate only what the product surfaces: the top manufacturers by
`dtc_codes` count (Dodge, Chrysler, Jeep, Chevrolet, Ford, …). Manufacturer codes are often
brand-jargon; reviewers may keep the English statement and translate only the description.

### Batch 3 — PIDs and component labels

PID names (`pid_texts`) and component labels are short and highly reusable; they are cheaper than
codes and make the UI feel native.

## Quality gates (enforced by the build, not by convention)

| Gate | Rule |
| --- | --- |
| `T001` (planned) | an `ar` definition must have a non-empty title |
| `T002` (planned) | `translation_reviewed = 1` requires `translator` and `reviewer` and `reviewer ≠ translator` |
| `T003` (planned) | the Arabic definition must target an existing `(code, context)` — no free-floating text |
| already enforced | only reviewed entries are loaded; every entry writes a `human_translation` claim |
| already enforced | the English statement stays canonical for `en`; Arabic becomes canonical for `ar` only |

## Review protocol

1. Translator works code-by-code from the English canonical statement *and* the causes, not from the
   code alone.
2. Reviewer checks: technical accuracy, glossary compliance, no invented remedy, no brand names.
3. A second reviewer is required for anything in the top 100 codes by prevalence.
4. Rejections are written back into the batch file with a `rejected_reason` (the loader ignores extra
   keys today; phase-2 adds the field).

## Measurement

The data report already tracks `codes_with_arabic` and `arabic_definitions` (currently 0). Phase 2
adds to `autodoctor report`:

* coverage by risk level: `arabic_high_risk / total_high_risk`;
* coverage of the generic layer;
* a list of the top 200 codes still missing Arabic (the translation backlog).

Release notes must quote these numbers; the project does not estimate coverage.

## Licensing

Translations are contributed under CC-BY-SA-4.0 (recorded in `data_sources` as
`local-translations`), so the database keeps one coherent share-alike term once autodiag2 or OBDb
enter the public set. Translators must be credited in `translations.translator` and in the app's
"About the data" screen.
