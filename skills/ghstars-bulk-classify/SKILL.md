---
name: ghstars-bulk-classify
description: |
  Classify active GitHub Stars from a managed local classification run. Use
  this skill for a one-time or resumed classification debt pass. It resumes
  valid proposals and user selections, refreshes changed source data when
  requested, and presents ten pending Stars at a time. Do not use it for normal
  Star discovery or automatic taxonomy repair.
---

# ghstars classify

Use this skill only inside an agent harness. The harness is the only part that
runs the LLM classification step. The deterministic ghstars commands can run
separately.

## Hard rules

- Get approval before each `ghstars sync` call.
- Stop if the fresh sync fails.
- Give only data from `classifier-input.jsonl` to the classifier.
- Do not read README files, repository topics, or web pages.
- Do not show current Lists or blessed Categories to the classifier.
- Use the exact `owner/name` value as the join key.
- Keep Intent as a low-confidence guess.
- Return exactly three ranked Category proposals per repository.
- Never apply a proposal without final user approval.
- Never assume that Replace means remove all current Lists.
- Require the user to name every List removed by a replacement.
- Do not bless a Category as a side effect.

## Workflow

### 1. Resume first, then create or refresh the run

Use a stable provider and model identifier for `CLASSIFIER`. Keep that value
for all batches in the run.

First call `extract` without `--new`:

```sh
ghstars classify extract --classifier "$CLASSIFIER" --json
```

This command selects the valid active run. Do not ask for a sync before this
check. Read `action`, `snapshot`, `resume_path`, and all progress counts.

If `action` is `resume`, tell the user that an existing run is available.
Ask: “A sync is available. Do you want to run it and resume the existing run?”

- If the user says yes, run `sync`, then run `extract` again without `--new`.
- If the user explicitly requests a new run, run `extract` with `--new`.
- If the user says no without requesting a new run, do not run a command. Suggest
  that the user request a new run if the existing run is not wanted.

If `action` is `new`, ask for sync approval before creating classifier input.
Stop if the user declines. Then run:

```sh
ghstars sync --json
ghstars classify extract --classifier "$CLASSIFIER" --json
```

Stop if the sync fails. If `action` is `refresh`, use the returned
`resume_path` and continue with the refreshed run.

The `action` value has these meanings:

- `new`: No reusable active run existed.
- `resume`: The command selected a reusable active run.
- `refresh`: A fresh sync changed the source snapshot.

A refresh keeps proposals for unchanged classifier facts. It also keeps user
selections for those proposals. It removes archived Stars and adds new Stars.
It invalidates every prior reconciliation plan and approval.

Use `--new` only after the user asks to discard reusable work:

```sh
ghstars classify extract --new --classifier "$CLASSIFIER" --json
```

Use `--resume PATH` only when the user names an older run. The CLI validates
and refreshes that run before use.

Set `WORK_DIR` to `resume_path`. The run can contain these files:

```text
$WORK_DIR/manifest.json
$WORK_DIR/classifier-input.jsonl
$WORK_DIR/proposals.jsonl
$WORK_DIR/reviews.jsonl
$WORK_DIR/run.json
```

Give only `classifier-input.jsonl` records to the classifier. Keep all work
files and review reports in `WORK_DIR`.

### 2. Classify in bounded batches

Compare `classifier-input.jsonl` with the accepted repository keys in
`proposals.jsonl`. Classify only repositories without an accepted proposal.
Read those records in bounded batches. For each repository, return one JSON
object with this exact shape:

```json
{
  "repo": "owner/name",
  "intent": {"value": "Explore", "score": 34},
  "categories": [
    {"value": "CLI", "score": 91},
    {"value": "Tool", "score": 82},
    {"value": "Example", "score": 55}
  ]
}
```

Rules:

- Copy `repo` exactly.
- Use one of `Explore`, `Current`, `Retired`, `Reference`, or `Learn`.
- Treat the Intent score as low confidence.
- Return exactly three distinct Categories.
- Sort Categories by descending score.
- Use integer scores from 0 through 100.
- Do not limit Categories to the current taxonomy.
- Return no explanation or extra fields.

Write each batch to a temporary JSONL file. Enforce the shape through ghstars:

```sh
ghstars classify write \
  --work-dir "$WORK_DIR" \
  --snapshot "$SNAPSHOT" \
  --input "$BATCH_FILE" \
  --json
```

Do not write `proposals.jsonl` by hand. The command validates repository keys,
scores, rank order, duplicate Categories, snapshot identity, and conflicting
retries.

### 3. Render and present ten items at a time

After every active Star has a proposal, render the next ten pending Stars:

```sh
ghstars classify render \
  --work-dir "$WORK_DIR" \
  --output "$OUTPUT" \
  --pending \
  --limit 10 \
  --threshold 70 \
  --json
```

Show the Markdown output to the user. Do not show the full report at once.
The command excludes repositories with stored review decisions. Keep the same
`WORK_DIR` and snapshot for each review batch.

Read the Markdown output. It has one block for each repository. Each block
has a stable number and the facts that the user needs for review:

```markdown
## 1. owner/name
- **Description:** A command-line tool for example tasks.
- **Language:** Python
- **Current Lists:** Explore: Tool
- **Target Classifications:** Intent guess: Explore (34); A. CLI (91); B. Tool (82); C. Example (55)
```

A Category below the threshold remains `Unclassified`. The threshold does not
make an adoption decision.

### 4. Ask for user selections

Show only the current ten-item review batch. Ask the user to select numbered
items and choices, for example:

```text
Adopt 1A, 5C, 43B. Skip 2-4.
```

A selection identifies a proposal. It does not authorize a mutation.

For each selected item, confirm the final Intent. The displayed Intent is only
a low-confidence guess. Store all selected and skipped decisions in a JSONL
batch:

```json
{"repo":"owner/name","status":"selected","choice":"A","intent":"Reference"}
{"repo":"owner/skip","status":"skipped","choice":null,"intent":null}
```

Pass the batch through the CLI:

```sh
ghstars classify review \
  --work-dir "$WORK_DIR" \
  --snapshot "$SNAPSHOT" \
  --input "$REVIEW_BATCH" \
  --json
```

Do not write `reviews.jsonl` by hand. The command validates repository keys,
accepted proposals, choices, confirmed Intents, and snapshot identity.

Render the next pending batch after each accepted review batch. Continue until
`pending` is zero. Repository keys preserve decisions if item numbers change.

For each selected repository, ask for or confirm:

1. `Add`, `Replace`, or `Skip`.
2. Every current List to remove for `Replace`.
3. Public or private status if a new List will be created.
4. Whether an unblessed Category can be added to the taxonomy.

### 5. Build the action plan

Compare each selected target with the hidden current mapping in `manifest.json`.
Use these mechanical states:

- `already_present`: the target membership exists.
- `addition`: keep current memberships and add the target.
- `same_category_change`: the Category exists under another Intent.
- `lifecycle_conflict`: the target conflicts with another lifecycle Intent.
- `new_list`: no matching target List exists.
- `unblessed`: the Category is outside the current vocabulary.

Do not choose an action for the user. Present an exact plan containing:

- repository name
- final Intent and Category
- Add, Replace, or Skip
- source Lists removed by Replace
- target List name
- public/private setting
- exact `ghstars tag` and `ghstars untag` commands
- any taxonomy blessing command

For replacement, add the target before separate removals. This keeps the Star
classified if a later removal fails. Show any sibling removal that `tag` will
perform for a lifecycle change.

### 6. Get final approval

Ask for one final approval of the complete plan. Do not run any mutation before
that approval.

If the user changes the plan, rebuild it and show it again. Do not reuse a
previous approval after the plan changes.

### 7. Recheck freshness and apply explicit operations

Ask for approval to run one more fresh sync immediately before mutation. This
approval is required even when the run resumed without a fresh sync:

```sh
ghstars sync --json
ghstars classify check --work-dir "$WORK_DIR" --json
```

Stop if the sync fails. If `matches` is false, do not use the approved plan.
Run `classify extract` without `--new`. The refresh keeps valid selections.
Rebuild the reconciliation plan from the new manifest. Get new final approval.

Run only explicit commands for approved repository names. Use existing ghstars
commands. Never turn a Filter, search, or report selection into an implicit
mutation target.

Stop on an unexpected failure or state drift. Report completed and pending
operations separately. Run `ghstars sync` after successful GitHub mutations.
Report the resulting state.

## Re-run behavior

Start each skill session by calling `extract` without `--new`. If it returns
an existing run, ask whether to sync and resume it. If the user says no,
accept `--new` only after an explicit request. If no reusable run exists, get
sync approval and then extract again.

A refresh can change item numbers. Use repository keys in `reviews.jsonl` to
preserve decisions. Never apply item tokens from an older snapshot. Use the
returned `resume_path` even if a refresh changes it.

A changed repository description or classifier fact invalidates its proposal
and review. A List-only change preserves the proposal and review. It invalidates
the reconciliation plan.

An identical proposal retry is safe. A different proposal for the same
repository is a conflict and must be reviewed again. Do not delete superseded
runs. They are audit records.

## Output

Report:

- persistent work directory and resume path
- snapshot ID
- number of active Stars
- number of proposals accepted
- number below the threshold
- Markdown report path
- user-approved operations
- completed operations and failures

Do not claim that a Category was adopted until the explicit application and
follow-up sync succeed.
