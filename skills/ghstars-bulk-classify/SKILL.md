---
name: ghstars-bulk-classify
description: |
  Classify active GitHub Stars from a managed local classification run. Use
  this skill for a one-time or resumed classification debt pass. It preserves
  valid proposals and review decisions when source data changes. It presents
  ten pending Stars at a time. Do not use it for normal Star discovery or
  automatic taxonomy repair.
---

# ghstars bulk classify

Use this skill only inside an agent harness. The harness performs the LLM
classification. The `ghstars classify` commands perform deterministic work.

## Safety rules

- Get approval before every `ghstars sync` call.
- Stop when a sync fails or the user declines it.
- Give only `classifier-input.jsonl` records to the classifier.
- Do not give current Lists or blessed Categories to the classifier.
- Do not read repository content or web data for classification.
- Keep the classifier and model constant for one run.
- Use the exact `owner/name` value as the repository key.
- Treat each Intent as a low-confidence guess.
- Do not apply a proposal without final approval.
- Do not infer which Lists a replacement removes.
- Do not bless a Category without a separate user decision.

## Workflow

### 1. Synchronize and select a run

Set `CLASSIFIER` to the current provider and model identifier. Keep this value
for the complete run.

Ask for approval to run a fresh sync. Do not extract before this approval.

```sh
ghstars sync --json
```

Stop if the user declines or the sync fails. Then run `extract` without
`--new`:

```sh
ghstars classify extract --classifier "$CLASSIFIER" --json
```

The command returns `action`, `snapshot`, `resume_path`, and progress counts.
Use `resume_path` as `WORK_DIR`. Use `snapshot` as `SNAPSHOT`.

The `action` value has these meanings:

- `new`: No reusable active run exists.
- `resume`: The command selected a matching active run.
- `refresh`: Local data changed, so the command created a refreshed run.

A refresh keeps valid proposals and review decisions. It invalidates each
earlier reconciliation plan and approval.

Use `--new` only when the user asks to discard reusable work. Use
`--resume PATH` only when the user selects an older run. Both forms still run
after the approved sync.

### 2. Classify missing proposals

Compare `classifier-input.jsonl` with the accepted keys in `proposals.jsonl`.
Classify only records without an accepted proposal. Process bounded batches.

Give the classifier only the selected `classifier-input.jsonl` records. For
each input record, produce one JSONL record with this shape:

```json
{"repo":"owner/name","intent":{"value":"Explore","score":34},"categories":[{"value":"CLI","score":91},{"value":"Tool","score":82},{"value":"Example","score":55}]}
```

Apply these rules:

- Copy `repo` exactly.
- Use `Explore`, `Current`, `Retired`, `Reference`, or `Learn` as Intent.
- Return exactly three distinct, non-empty Categories.
- Sort Categories by descending score.
- Use integer scores from 0 through 100.
- Permit Categories outside the blessed vocabulary.
- Return no explanations or extra fields.

Write each batch to a temporary JSONL file. Pass the file through the CLI:

```sh
ghstars classify write \
  --work-dir "$WORK_DIR" \
  --snapshot "$SNAPSHOT" \
  --input "$BATCH_FILE" \
  --json
```

Do not write `proposals.jsonl` directly. Stop and report a validation or
conflict error.

### 3. Review ten pending Stars

After all active Stars have proposals, render the next review batch:

```sh
ghstars classify render \
  --work-dir "$WORK_DIR" \
  --output "$OUTPUT" \
  --pending \
  --limit 10 \
  --threshold 70 \
  --json
```

Show the rendered Markdown. Do not show more than ten pending Stars. A score
below the threshold marks a Category as unclassified. It does not make a user
decision.

Ask the user to select a Category or skip each displayed Star. Accept tokens
such as `adopt 1A, 5C` and `skip 2-4`. A selection does not authorize a
mutation.

Confirm or replace the Intent for each selected Star. Store decisions by
repository in a temporary JSONL file:

```json
{"repo":"owner/name","status":"selected","choice":"A","intent":"Reference"}
{"repo":"owner/skip","status":"skipped","choice":null,"intent":null}
```

Pass the file through the CLI:

```sh
ghstars classify review \
  --work-dir "$WORK_DIR" \
  --snapshot "$SNAPSHOT" \
  --input "$REVIEW_BATCH" \
  --json
```

Do not write `reviews.jsonl` directly. Render the next batch. Continue until
no pending reviews remain. Use repository keys, not old item numbers, after a
refresh.

### 4. Resolve each selected target

Compare selected targets with the current mapping in `manifest.json`. Keep
that mapping hidden from the classifier.

Report these mechanical states when they apply:

- `already_present`: The target membership exists.
- `addition`: The target adds a membership.
- `same_category_change`: The Category exists under another Intent.
- `lifecycle_conflict`: The target conflicts with another lifecycle Intent.
- `new_list`: The target List does not exist.
- `unblessed`: The Category is outside the current vocabulary.

Ask the user to choose `Add`, `Replace`, or `Skip` for each target.

- `Add` keeps all current memberships.
- `Replace` removes only Lists that the user names.
- `Skip` makes no change.

For a new List, ask whether it is public or private. For an unblessed Category,
ask the user to bless it, select another proposal, or skip it. Never infer
these decisions.

### 5. Build and approve the plan

Present one exact plan for all selected targets. Include:

- the repository, final Intent, and Category
- the Add, Replace, or Skip decision
- each List that Replace removes
- the target List and its privacy
- each `ghstars taxonomy bless`, `ghstars tag`, and `ghstars untag` command
- each operation that can create a List

For a replacement, add the target before separate removals. Show a sibling
removal that `tag` performs during a lifecycle change.

Ask for final approval of the complete plan. If the plan changes, rebuild it
and request new approval. Do not mutate GitHub yet.

### 6. Check freshness and apply

Ask for approval to run another fresh sync. Then run:

```sh
ghstars sync --json
ghstars classify check --work-dir "$WORK_DIR" --json
```

Stop if the sync fails. If `matches` is false, do not use the approved plan.
Run `classify extract` without `--new`. Use its returned `resume_path` and
snapshot. Rebuild the plan from the refreshed manifest. Request final approval
again.

Run only the explicit commands in the current approved plan. Use only approved
repository names. Stop after an unexpected result or state drift. Report
completed and pending operations separately.

Ask for approval before the final sync. After approval, run `ghstars sync
--json` and report the resulting state. Do not claim adoption before the
mutation and final sync succeed.

## Report

Report:

- the persistent work directory and snapshot ID
- active, accepted, pending, and below-threshold counts
- the review report path
- the approved operations
- completed operations, pending operations, and failures

Do not delete superseded runs. They are audit records.
