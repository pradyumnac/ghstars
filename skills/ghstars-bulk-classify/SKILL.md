---
name: ghstars-bulk-classify
description: |
  Classify active GitHub Stars from a managed local classification run. Use
  this skill for a one-time or resumed classification debt pass. It preserves
  valid proposals and review decisions when source data changes. It presents
  a user-selected number of pending Stars at a time. Do not use it for normal
  Star discovery or
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
- Present each review report in the exact format from `classify render`.
- Do not use command output as the user-facing review report.
- Do not summarize, shorten, reformat, or omit report fields.

## Workflow

### 1. Synchronize and select a run

Set `CLASSIFIER` to the current provider and model identifier. Keep this value
for the complete run.

Before the first command, show these run assumptions:

- the classifier identifier
- whether the run includes only unclassified Stars or all active Stars
- the maximum number of Stars, or `all` when there is no limit
- the review batch size, from 1 through the selected Star count
- whether prior proposals and reviews can be reused

Ask for the review batch size before run confirmation. Accept a value from 1
through the selected Star count. If the value is greater than 50, immediately
show this warning:

> Generating and displaying more than 50 classifications can be time-consuming
> and token-expensive. Do you want to continue?

Ask the user to select `Yes, continue` or `Choose a smaller batch`. Do not
reject or reduce the requested batch size. Continue with the requested size
only after the user selects `Yes, continue`. If the user selects
`Choose a smaller batch`, ask for a new batch size.

Ask the user to confirm the assumptions. By default, include only Stars with no
Category or only `General`. Include classified Stars only when the user asks to
redo them. Apply a requested limit after this scope filter.

Ask for approval to run a fresh sync. Do not extract before this approval.

```sh
ghstars sync --json
```

Stop if the user declines or the sync fails. Then run `extract` without
`--new`:

```sh
ghstars classify extract \
  --classifier "$CLASSIFIER" \
  --unclassified-only \
  --limit "$LIMIT" \
  --json
```

Omit `--limit` when the user approves all matching Stars. Omit
`--unclassified-only` only when the user asks to redo classified Stars.

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

Compare `classifier-input.jsonl` repository keys with `proposal.repo` in each
`proposals.jsonl` envelope. Classify only records without an accepted proposal.
Process bounded batches.

Give the classifier only the selected `classifier-input.jsonl` records. For
each input record, produce one JSONL record with this shape:

```json
{"repo":"owner/name","intent":{"value":"Explore","score":34},"categories":[{"value":"Tool - Developer Workflow","score":91},{"value":"Library - Web Development","score":82},{"value":"Example - Dotfiles","score":55}]}
```

Apply these rules:

- Copy `repo` exactly.
- Use `Explore`, `Current`, `Retired`, `Reference`, or `Learn` as Intent.
- Return exactly three distinct, non-empty Categories.
- Format every Category as `<Type> - <Specific purpose>`.
- Choose the Type from this list:
  - `Application`: A complete program for an end user.
  - `Service`: A hosted, networked, or background system.
  - `Tool`: A focused utility that performs a task.
  - `Library`: Reusable code that another program imports.
  - `Framework`: A foundation that controls an application's structure.
  - `Plugin`: An extension for another application or platform.
  - `Example`: A demonstration, tutorial, or reference implementation.
  - `Configuration`: Settings or dotfiles for another system.
  - `Documentation`: Explanatory or reference content.
  - `Dataset`: A machine-readable data collection.
  - `Theme`: Visual styles for another application or platform.
- Describe the main user utility as the Specific purpose.
- Do not use a programming language, `Open Source`, `Software`, `General`,
  or a Type without a Specific purpose.
- Do not use bare `AI`; use a specific value such as `Tool - AI Coding`.
- Use `Configuration - Dotfiles` for personal configuration repositories.
  Use `Example - Dotfiles` only for repositories that demonstrate a setup.
- Prefer utility-driven names such as `Tool - Note Taking`,
  `Service - Self Hosting`, `Tool - Backup`, or `Tool - Hardware Driver`.
- Give a low score when no strong user purpose matches.
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

### 3. Review pending Stars

Use the approved review batch size from the run assumptions. Set
`REVIEW_BATCH_SIZE` to that value.

After all Stars in the selected run have proposals, render the next review
batch:

```sh
ghstars classify render \
  --work-dir "$WORK_DIR" \
  --output "$OUTPUT" \
  --pending \
  --limit "$REVIEW_BATCH_SIZE" \
  --threshold 70 \
  --json
```

After the command succeeds, read the file at `OUTPUT`. Copy the complete file
into a user-facing assistant message. Present the Markdown exactly as the
renderer produced it. Do not rely on command output to present the report. Do
not summarize or reformat the report. Do not remove descriptions, languages,
current Lists, Intent guesses, scores, headings, or classification choices. Do
not ask for review decisions until the complete report is visible. Do not show
more than `REVIEW_BATCH_SIZE` pending Stars.

If a platform output limit requires multiple messages, split the report only
between repository entries. Label each message as a report part. Do not ask for
decisions until all parts are visible. Do not reduce the approved batch size.

When Category A is below the threshold, the renderer marks the repository
target as unclassified. This marker does not make a user decision.

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

Do not write `reviews.jsonl` directly. Render the next batch with
`REVIEW_BATCH_SIZE`. Continue until no pending reviews remain. Use repository
keys, not old item numbers, after a refresh.

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

A proposal value is a Category, not a List name. Bless only the Category value.
Build a target List as `{Intent}: {Category}`. A bare existing List implies the
`Reference` Intent. Reuse its exact name when it matches the approved target.
Use the explicit form when a new List is required.

For a new List, ask whether it is public or private. After all target decisions,
collect the distinct unblessed Categories. Show the count and the complete
Category list. Ask the user to approve that blessing set. The user can remove a
Category, select another proposal, or skip its repositories. Never infer these
decisions.

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
Run `classify extract` without `--new`. Pass the same `--classifier`, scope,
and limit arguments as the approved run assumptions. Use its returned
`resume_path` and snapshot. Rebuild the plan from the refreshed manifest.
Request final approval again.

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
