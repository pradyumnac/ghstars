---
name: ghstars-bulk-classify
description: |
  Classify active GitHub Stars from ghstars local pull data. Use this skill for
  a one-time or occasional classification debt pass. It reads only stored Star
  and List data, asks the agent to propose one low-confidence Intent and three
  ranked Categories, and presents a numbered Markdown review table. Do not use
  it for normal Star discovery, synchronization, or automatic taxonomy repair.
---

# ghstars classify

Use this skill only inside an agent harness. The harness is the only part that
runs the LLM classification step. The deterministic ghstars commands can run
separately.

## Hard rules

- Read only data already stored by ghstars.
- Do not read README files, repository topics, web pages, or GitHub APIs.
- Do not show current Lists or blessed Categories to the classifier.
- Use the exact `owner/name` value as the join key.
- Keep Intent as a low-confidence guess.
- Return exactly three ranked Category proposals per repository.
- Never apply a proposal without final user approval.
- Never assume that Replace means remove all current Lists.
- Require the user to name every List removed by a replacement.
- Do not bless a Category as a side effect.

## Workflow

### 1. Create a runtime work directory

Ask for or create a temporary directory. Do not use a fixed project path.
Keep the directory if the user wants an audit record.

```sh
ghstars classify extract --work-dir "$WORK_DIR" --json
```

Read the returned `snapshot` and `count`.

The command writes:

```text
$WORK_DIR/manifest.json
$WORK_DIR/classifier-input.jsonl
```

`classifier-input.jsonl` is the only file sent to the classifier.

### 2. Classify in bounded batches

Read `classifier-input.jsonl` in bounded batches. For each repository return
one JSON object with this exact shape:

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

### 3. Render the numbered review table

After every active Star has a proposal, render the report:

```sh
ghstars classify render \
  --work-dir "$WORK_DIR" \
  --output "$OUTPUT" \
  --threshold 70 \
  --json
```

Read the Markdown output. It has exactly three columns and one stable numbered
row per active Star:

```markdown
| Repository | Current Lists | Target Classifications |
| --- | --- | --- |
| 1. owner/name | Explore: Tool | Intent guess: Explore (34); A. CLI (91); B. Tool (82); C. Example (55) |
```

A Category below the threshold remains `Unclassified`. The threshold does not
make an adoption decision.

### 4. Ask for user selections

Show the numbered table. Ask the user to select rows and choices, for example:

```text
Adopt 1A, 5C, 43B. Skip 2-4.
```

A selection identifies a proposal. It does not authorize a mutation.

For each selected row, ask for or confirm:

1. The final Intent. The displayed Intent is only a low-confidence guess.
2. `Add`, `Replace`, or `Skip`.
3. Every current List to remove for `Replace`.
4. Public or private status if a new List will be created.
5. Whether an unblessed Category can be added to the taxonomy.

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

### 7. Apply explicit operations

Run only explicit commands for approved repository names. Use existing ghstars
commands. Never turn a Filter, search, or table selection into an implicit
mutation target.

Stop on an unexpected failure or state drift. Report completed and pending
operations separately. Run `ghstars sync` after successful GitHub mutations and
report the resulting state.

## Re-run behavior

The runtime snapshot owns row numbering. A new extraction creates a new snapshot
and can change row numbers. Do not apply an old selection to a new snapshot.

An identical proposal retry is safe. A different proposal for the same
repository is a conflict and must be reviewed again.

## Output

Report:

- work directory
- snapshot ID
- number of active Stars
- number of proposals accepted
- number below the threshold
- Markdown report path
- user-approved operations
- completed operations and failures

Do not claim that a Category was adopted until the explicit application and
follow-up sync succeed.
