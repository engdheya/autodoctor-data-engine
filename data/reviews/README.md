# Conflict review decisions

`conflicts.yaml` in this directory is the **only** place where the engine records a human
judgement about a disagreement between sources. It is committed on purpose: a decision must
survive a rebuild, and a reviewer must be able to audit it in git history.

* empty `decisions: []` means nothing has been reviewed yet — all conflicts stay `needs_review`;
* each decision carries the fingerprint, the reviewer, the timestamp and the reason;
* decisions are applied by **content**, so new upstream wording needs a new review.

```bash
autodoctor list-conflicts                    # the queue, with fingerprints
autodoctor review-conflict <fingerprint> --accept --note "…" --reviewer "…"
autodoctor review-conflict <fingerprint> --resolve --source obdex --note "…" --reviewer "…"
```

Full explanation: [docs/CONFLICT_REVIEW.md](../../docs/CONFLICT_REVIEW.md).
