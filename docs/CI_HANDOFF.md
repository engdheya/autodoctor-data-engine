# CI handoff — one manual step required

The workflow files are written and stored in `ci/`, but this session runs as a
GitHub App **without the `workflows` permission**, so any push touching
`.github/workflows/*` is rejected by GitHub:

```
refusing to allow a GitHub App to create or update workflow
`.github/workflows/ci.yml` without `workflows` permission
```

That is a permission limit of the automation, not a defect in the workflow. The
suite it would run is green locally (231 tests, 5 skipped, `ruff check .` clean).

## What to do (2 minutes, either option)

**Option A — commit the files yourself.** In a local clone of `main`:

```bash
mkdir -p .github/workflows
cp ci/ci.yml .github/workflows/ci.yml
cp ci/upstream-drift.yml .github/workflows/upstream-drift.yml
git add .github/workflows && git commit -m "ci: run tests on push and pull request"
git push origin main
```

**Option B — grant the App `workflows` permission** for this repository, then ask
for the workflow commit to be retried; the file contents are already final.

## What the workflows do

| Workflow | Trigger | Jobs |
| --- | --- | --- |
| `ci.yml` | push to `main`, every pull request | `ruff check`, `ruff format --check`, `pytest` on Python 3.11/3.12/3.13, project-level checks |
| `upstream-drift.yml` | schedule | re-fetches the upstream sources and reports whether any pinned commit moved |

Until this lands, "tests run automatically" is **not** satisfied; the test evidence
in the release notes is a local run.

## Repository setting that also needs a human

Branch protection on `main` (require the `quality` check before merge) can only be
enabled by an owner with admin rights:

```bash
gh api -X PUT repos/engdheya/autodoctor-data-engine/branches/main/protection \
  -f 'required_status_checks[strict]=true' \
  -f 'required_status_checks[contexts][]=quality' \
  -f 'enforce_admins=true' -f 'restrictions=' -F 'required_pull_request_reviews='
```
