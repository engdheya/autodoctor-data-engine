# CI definitions

GitHub only runs workflows from `.github/workflows/`, but the GitHub App that pushes to this
repository during the current session does not have the `workflows` permission, so these files are
kept here and must be activated once by a maintainer:

```bash
mkdir -p .github/workflows
cp ci/ci.yml ci/upstream-drift.yml .github/workflows/
git add .github/workflows && git commit -m "ci: activate workflows" && git push
```

| File | Runs | What it does |
| --- | --- | --- |
| `ci.yml` | every push to `main` and every PR | `ruff check` + `pytest` on Python 3.11/3.12/3.13, plus a job that installs the CLI (no sources needed), checks `autodoctor --help`/`version`, and verifies every relative documentation link resolves |
| `upstream-drift.yml` | Mondays 04:00 UTC + manual | fetches the four sources, inspects their real layouts, imports a bounded slice, uploads `data/reports/source-inspection.json` and opens an issue when a source changes shape or disappears |

Both workflows are self-contained: they install the package with `pip install -e .` and never need
secrets, databases or network access to third-party services beyond GitHub itself.
