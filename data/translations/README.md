# Human translations

The engine **never machine-translates** and no upstream source provides Arabic. Translations are
human work and they are loaded with the translator and reviewer attached.

## Workflow

```bash
# 1. export the codes that are still missing a translation, in priority order
autodoctor export-translation-template --lang ar --limit 2000
#    -> data/reports/translation-template-ar.csv

# 2. a translator fills title_ar (and optionally description_ar) and saves as YAML
#    data/translations/ar/<batch>.yaml     (format: see example.yaml)

# 3. a reviewer sets `reviewed: true` and names themselves in `reviewer`

# 4. rebuild; only reviewed entries are applied
autodoctor build-db --version 0.1.1
```

Entries that are not `reviewed: true`, or that have no `reviewer`, are **skipped and reported** by
`build-db` — they never reach the database silently.

## What happens to a reviewed entry

* a `dtc_definitions` row with `language: ar`, `is_translated: 1`, `translation_reviewed: 1`;
* a `translations` row with translator, reviewer and source URL;
* a `provenance_claims` row with `extraction_method: human_translation` and the translator/reviewer
  in `notes`;
* the Arabic-only definition becomes canonical for `ar` (English stays canonical for `en`).

## Rules

1. Translate the *meaning of the code*, never a guessed remedy.
2. Keep the original equipment abbreviations (ECU, PCM, B1S1, DPF) or transliterate them once and
   stay consistent; put the English term in parentheses on first use.
3. Do not translate a statement the reviewer cannot verify against the English text.
4. One file per batch and language; `code` must exist in the database (`V001` code format applies).
5. Licence: translations are contributed under CC-BY-SA-4.0 so that the database has one coherent
   share-alike term (see `docs/LICENSES.md`).
