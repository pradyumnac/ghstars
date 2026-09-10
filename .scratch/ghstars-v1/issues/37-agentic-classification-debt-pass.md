# 37 — Agentic classification debt pass

**What to build:** Add a dedicated agent skill and deterministic helper
commands. The skill classifies every active Star from stored pull data. It
proposes three ranked classifications, then writes a three-column Markdown
report.

**Status:** implemented — offline extraction, proposal validation, deterministic
rendering, CLI commands, and the dedicated skill are in place. The user must
approve every adoption plan before implementation.

**Kind:** enhancement

**Blocked by:** None. This ticket is separate from ticket 14. Ticket 14 covers
normal ghstars operations. This ticket covers a one-time or occasional debt
correction pass.

## Purpose and limits

Use this workflow to correct accumulated classification debt. Do not make it a
continuous sync feature. The complete workflow runs only inside an agent
harness, because one step requires an LLM.

Each deterministic component can run by itself. Classification reads no
GitHub data and fetches no repository content. The adoption phase can change
GitHub only after two explicit user decisions.

The LLM does not see blessed Categories, current Lists, or current Categories.
It sees only stored repository facts. This separation prevents the current
taxonomy from anchoring the proposals.

## Data-flow diagram

```text
┌──────────────────────────────────────────────┐
│ [A. Stored Pull Data]                        │
│                                              │
│ state/stars.json                             │
│ state/lists.json                             │
│ No network access                           │
└─────────────────────┬────────────────────────┘
                      │ offline read
                      ▼
┌──────────────────────────────────────────────┐
│ [B. Runtime Extraction]                      │
│                                              │
│ ghstars classify extract --work-dir PATH     │
│ Caller defines PATH at runtime.              │
│ Command writes one stable snapshot.          │
└───────────────┬──────────────────┬───────────┘
                │                  │
                │ LLM-visible      │ hidden deterministic data
                ▼                  ▼
┌────────────────────────────┐  ┌─────────────────────────────┐
│ [C. Classifier Input]      │  │ [D. Current Mapping]        │
│                            │  │                             │
│ repo: owner/name           │  │ repo → current List names   │
│ description                │  │ repo → current Categories   │
│ language and stored facts  │  │ snapshot identifier         │
│                            │  │                             │
│ No current classification  │  │ LLM does not see this data. │
│ No blessed vocabulary      │  └──────────────┬──────────────┘
└──────────────┬─────────────┘                 │
               │                               │
               ▼                               │
┌──────────────────────────────────────────────┐
│ [E. LLM Classification]                      │
│                                              │
│ Skill supplies Intent and Category rules.    │
│ LLM returns one low-confidence Intent guess. │
│ LLM returns three ranked Category proposals. │
└─────────────────────┬────────────────────────┘
                      │ strict JSONL
                      ▼
┌──────────────────────────────────────────────┐
│ [F. Enforced Proposal Write]                 │
│                                              │
│ ghstars classify write --work-dir PATH       │
│                         --snapshot ID         │
│                         --input BATCH.jsonl   │
│                                              │
│ Validate every field and repository key.     │
│ Write accepted proposals atomically.         │
└─────────────────────┬────────────────────────┘
                      │ validated proposals
                      ▼
┌──────────────────────────────────────────────┐
│ [G. Deterministic Reconciliation]            │
│                                              │
│ ghstars classify render --work-dir PATH      │
│                          --output PATH        │
│                          --threshold SCORE    │
│                                              │
│ Join on exact owner/name.                     │
│ Add current Lists and current Categories.     │
│ Apply Category confidence threshold.          │
└─────────────────────┬────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────┐
│ [H. Numbered Review Table]                   │
│                                              │
│ Three columns; one numbered row per Star.     │
│ Show Intent guess and Category choices A-C.   │
│ User is the primary decision-maker.           │
└─────────────────────┬────────────────────────┘
                      │ user selects rows and choices
                      ▼
┌──────────────────────────────────────────────┐
│ [I. User Selection]                          │
│                                              │
│ Examples: adopt 1A, 5C, 43B                  │
│           skip 2, 3, 4                       │
│ User confirms or overrides each Intent.       │
└─────────────────────┬────────────────────────┘
                      │ selected targets only
                      ▼
┌──────────────────────────────────────────────┐
│ [J. Add-or-Replace Reconciliation]            │
│                                              │
│ Compare target with current memberships.      │
│ Ask: add, replace named Lists, or skip.        │
│ Never infer the replacement scope.            │
└─────────────────────┬────────────────────────┘
                      │ explicit action plan
                      ▼
┌──────────────────────────────────────────────┐
│ [K. Final User Approval]                     │
│                                              │
│ Show exact tag and untag operations.          │
│ Show new or unblessed Categories.             │
│ User gives the final adoption decision.       │
└─────────────────────┬────────────────────────┘
                      │ approved plan only
                      ▼
┌──────────────────────────────────────────────┐
│ [L. Explicit Application]                    │
│                                              │
│ Run explicit ghstars commands per repo.       │
│ Stop and report partial failures or drift.    │
│ Sync and present the resulting state.         │
└──────────────────────────────────────────────┘
```

## Runtime work directory

Node B requires `--work-dir PATH`. The project defines no default location.
The caller can use a temporary directory or a retained audit directory.

The directory contains these files:

```text
PATH/
├── manifest.json
├── classifier-input.jsonl
└── proposals.jsonl
```

`manifest.json` holds the snapshot identifier and the current mappings.
`classifier-input.jsonl` holds the LLM-visible records. `proposals.jsonl`
holds only records accepted by Node F.

The snapshot identifier is a content hash of the extracted active Stars and
Lists. Nodes F and G refuse work when the manifest does not match their input.

## Node C: classifier input shape

Use JSONL so the skill can process bounded batches without repeating an
envelope. Use the exact `owner/name` value as `repo`.

```json
{"repo":"owner/name","description":"Stored description","language":"Python","fork":false}
```

Include only fields that already exist in the stored pull data. Do not include
current List names, parsed Categories, or the blessed Category vocabulary.

Sort records by `repo`. Exclude Archived Stars.

## Node E: required LLM output shape

The LLM must return one JSONL record for each input record. Intent and Category
are independent predictions. The result contains one Intent guess and exactly
three Category proposals.

```json
{"repo":"owner/name","intent":{"value":"Explore","score":34},"categories":[{"value":"CLI","score":91},{"value":"Tool","score":82},{"value":"Example","score":55}]}
```

Apply these rules:

- Keep `repo` byte-for-byte equal to the input `owner/name` value.
- Return one Intent guess.
- Use only `Explore`, `Current`, `Retired`, `Reference`, or `Learn` as Intent.
- Treat the Intent score as low confidence.
- Return exactly three Category proposals.
- Use a non-empty free-text Category.
- Permit blessed and unblessed Categories.
- Use an integer score from 0 through 100 for each value.
- Sort Categories by descending score.
- Return three distinct normalized Categories.
- Return no explanation or additional fields.

Node F enforces this shape. The skill must not write directly to
`proposals.jsonl`. The skill passes the manifest identifier through
`--snapshot ID`. The command refuses an identifier that does not match the
runtime manifest.

The writer adds the verified snapshot identifier to each persisted record.
The LLM does not produce that field. Node G checks the persisted identifier
before it joins a record.

An identical repeated record is an idempotent success. A second record with
different proposals for the same `repo` is a conflict. The command refuses the
conflict instead of choosing one result.

## Node G: deterministic reconciliation

Use `repo` as the only join key. The key is the exact `owner/name` value from
the runtime snapshot.

The renderer must reject these conditions:

- A proposal names a repository outside the manifest.
- An active repository has no proposal.
- A repository has more than one different proposal record.
- The manifest or proposal snapshot identifier does not match.
- A current List ID cannot resolve through the manifest.

The renderer adds current List names and parsed Categories from
`manifest.json`. It makes no semantic choice during the join.

If Category A meets the threshold, mark it as eligible for review. If Category
A is below the threshold, keep the Star unclassified. Always show all three
Categories as review evidence. Never use the Intent score for automatic
selection.

## Node H: numbered Markdown shape

Write exactly three columns. Put the stable row number in the Repository cell.
Label the three Category choices `A`, `B`, and `C`.

```markdown
| Repository | Current Lists | Target Classifications |
| --- | --- | --- |
| 1. owner/name | Explore: Tool | Intent guess: Explore (34); A. CLI (91); B. Tool (82); C. Example (55) |
| 2. owner/unclear | — | Unclassified; Intent guess: Reference (28); A. Protocol (58); B. Tool (44); C. Library (31) |
```

Escape pipes, newlines, and Markdown control characters. Keep repository order
stable. Write one row for every active Star in the manifest.

The row number is stable only inside one runtime snapshot. The user selects a
proposal with the row number and choice letter, for example `1A` or `43B`.
The user can override the Intent during selection.

The current Categories remain structured join data. The report normally shows
the source List names because each List name retains its Intent and Category.
The renderer uses parsed Categories for validation and action planning.

## Agent skill

Build a dedicated skill for this debt pass. Do not fold it into the normal
operational skill from ticket 14.

The skill performs these steps:

1. Ask the user for the runtime work directory, output path, and threshold.
2. Run Node B once.
3. Read Node C in bounded batches.
4. Run Node E inside the current agent harness.
5. Send each batch through Node F.
6. Run Node G after every Star has an accepted result.
7. Present the numbered Node H report and summary counts.
8. Accept selections such as `adopt 1A, 5C, 43B`.
9. Ask the user to confirm or override each low-confidence Intent.
10. Ask whether each selected target is an addition or a replacement.
11. Build an exact operation plan and present it without running it.
12. Run the plan only after the final user approval in Node K.
13. Synchronize and report the resulting state.

The helper commands remain usable without the skill. Only the skill provides
the end-to-end LLM orchestration and approval conversation.

## Adoption reconciliation

The user is the primary decision-maker. Selecting a row does not authorize a
mutation. It identifies a proposal for the action-planning step.

For each selected proposal, the skill determines one of these mechanical
states:

| State | Meaning |
| --- | --- |
| `already_present` | A current List already has the selected Intent and Category. |
| `addition` | The target adds a new Category and keeps all current Lists. |
| `same_category_change` | The Category exists, but its Intent differs. |
| `lifecycle_conflict` | Adding the target creates more than one lifecycle Intent. |
| `new_list` | No current List has the selected Intent and Category. |
| `unblessed` | The selected Category is outside the current vocabulary. |

The skill must not turn these states into an automatic policy. It asks the user
to choose one action:

- **Add:** Add the target and keep every current membership.
- **Replace:** Remove only the current Lists that the user names, then add the
  target.
- **Skip:** Make no change for this Star.

A replacement never means "remove all current Lists." The user must name each
List that will be removed. The skill shows lifecycle conflicts before it asks
for final approval.

An unblessed Category needs a separate user decision. The user can bless it,
choose another proposal, or skip it. The skill never blesses a Category as a
side effect.

If adoption creates a List, ask whether the List is public or private. Show the
choice in the final plan. Do not infer privacy from another List.

Node K shows every exact `tag`, `untag`, and taxonomy operation in execution
order. It also shows which operations can create a new List. The user then
gives one final approval for that plan.

For a replacement, add the approved target before separate `untag` operations.
This order keeps a Star classified if a later removal fails. A same-Category
lifecycle change can remove its sibling inside `tag`; show that expected removal
in the plan. Stop after any unexpected result, then show the partial state.

## Issues and safeguards

### 1. Intent has weak evidence

Intent describes the user's relationship to a Star. Repository metadata cannot
show whether the user currently explores, uses, retired, references, or learns
from it. Hiding current Lists removes the only stored relationship evidence.

The Intent guess stays in the output with its own score. Treat it as low
confidence. The user must confirm or replace it before adoption.

### 2. Free Categories can fragment

An unbounded vocabulary can produce synonyms such as `CLI`, `Command Line`,
and `Terminal Tool`. This behavior is useful for taxonomy discovery, but it is
not ready for automatic application.

Keep the report advisory. Add no automatic synonym merge to this ticket.

### 3. Scores are not calibrated across batches

An LLM score from one batch is not guaranteed to equal the same score from a
later batch. Use the threshold as a review aid, not as a measured probability.
Keep the prompt and model constant for one run.

### 4. Stored metadata is limited

The stored pull data has no README text or repository topics. A repository with
an empty or vague description will receive a weak classification. This limit is
intentional because the workflow must not read beyond stored pull data.

## Acceptance

- [x] Add the `ghstars classify` command group with `extract`, `write`, and
      `render` subcommands.
- [x] Require a runtime work directory. Add no fixed output location.
- [x] Keep Nodes A through H offline and non-mutating outside the runtime work
      directory.
- [x] Hide current classification and blessed Categories from the LLM input.
- [x] Enforce the Node E output shape through `classify write`.
- [x] Store separate scores for the Intent guess and each Category.
- [x] Join records only by exact `owner/name`.
- [x] Make extraction and report order deterministic.
- [x] Support safe batch accumulation and identical retries.
- [x] Reject missing, extra, duplicate, and drifted records.
- [x] Write the exact three-column, numbered Markdown report.
- [x] Keep low-confidence Stars unclassified.
- [x] Accept row-and-choice selections such as `1A` and `43B`.
- [x] Require the user to confirm or replace every selected Intent.
- [x] Ask for Add, Replace, or Skip for every selected target.
- [x] Require explicit source List names for each replacement.
- [x] Ask for public or private when an action creates a List.
- [x] Show the exact operation plan before any mutation.
- [x] Require final user approval before Node L.
- [x] Apply only explicit repository targets through existing ghstars commands.
- [x] Stop and report drift or partial failure in the skill workflow.
- [x] Build the dedicated agent-harness skill.
- [x] Test every deterministic command as an individual component.
- [x] Confirm that Nodes A through H never create a GitHub client or write
      ghstars state.

## Verification

Implemented on 2026-09-10.

Committed in `740795a` (`Add offline Star classification workflow`). The old
untracked `.scratch/ghstars-v1/triage/` sample data was not part of that commit
and was removed during cleanup.

- `ghstars classify extract --work-dir PATH --json` writes the runtime
  snapshot and classifier input.
- `ghstars classify write --work-dir PATH --snapshot ID --input BATCH.jsonl`
  validates and accumulates proposals.
- `ghstars classify render --work-dir PATH --output REPORT.md --threshold 70`
  writes the numbered three-column report.
- Focused classification and CLI tests pass.
- The full suite passes: 553 tests.
- `mise run check` passes: tests, Ruff, formatting, and mypy.
- LSP and pi-lens diagnostics pass for the changed implementation.

The skill lives at
`/home/doe/repos/env/ai/personal/ghstars-classify/SKILL.md`.
The end-to-end approval and adoption flow remains agent-harness work. The CLI
only performs the deterministic extraction, validation, join, and render
steps. It does not apply proposals.

## Corrective RCA pass

The first clean-context review found defects in the proposal and reconciliation
trust boundary. The corrective pass fixed them before the next commit:

- Extraction reads Stars and Lists under one local lock.
- Extraction rejects duplicate records, unresolved List IDs, and asymmetric
  membership.
- The manifest hash binds the manifest, classifier input, and current mapping.
- Proposal models reject extra fields and coerced score types.
- Work files and the Markdown report use atomic writes.
- Rendering rejects duplicate, missing, and unknown repository keys.
- Rendering follows manifest order, so row numbers stay stable.
- Markdown control characters are escaped.
- `classify extract --json` converts corrupt state and lock errors to the CLI
  error envelope instead of exposing a traceback.

The first code commit was `740795a`. The corrective commits are `a55d27e`
(`Harden classification reconciliation`) and `e8d2651` (`Prevent
classification side effects`). The skill is committed separately in the
`env/ai` repository as `3c10412` (`Add ghstars classification skill`).

Verification after the corrective pass: 559 tests pass, `mise run check` passes,
and Ruff and mypy pass.

## Comments

This design replaces the earlier three-slot pilot format. The old pilot mixed
one bounded Category with two free-text subject suggestions. This workflow
returns one low-confidence Intent guess and three free Category proposals under
one enforced schema.

The user accepted Intent as a low-confidence guess. The user remains the main
decision-maker and gives the final adoption approval.
