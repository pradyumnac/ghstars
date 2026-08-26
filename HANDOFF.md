# Handoff

Context from work sessions that does not live anywhere else yet. Everything
here is either an undecided question, a finding whose only record is a
commit message or a conversation, or a gap noticed while working that's out
of scope to fix right now.

Delete a section once it lands in `TODO.md`, an ADR, `AGENTS.md`, or
`README.md` — this file is a staging area, not a second source of truth.

## Task rail

Mirror of the session-scoped Task tool (`TaskCreate`/`TaskUpdate`/
`TaskList`/`TaskGet`) — see the `handoff` skill's "Task rail reconciliation"
and "Task rail mirroring" sections for the read/write rules. Always present,
even empty: a missing section looks identical to "nothing active," which
hides the difference between "no plan" and "forgot to mirror one."

Mirrors `.scratch/ghstars-v1/issues/*.md`, ticket-for-ticket (task ID N ==
ticket `NN`) where possible. The ticket files are the actual source of
truth (acceptance criteria, `## Comments` with implementation notes); this
table is a status snapshot only. Check harness `TaskList` for live status
if resuming with new tasks in flight.

### Done

Tickets 01–11, 16, 17, 19, 20, 21, 22, 29. Each ticket file's own
`Status: done` / `## Comments` is the source of truth for what shipped
and how — not duplicated here, per this file's own rule above (delete
once it lands elsewhere; ticket files already are "elsewhere").
Reconciled against the ticket files directly on 2026-08-26.

### Gaps to fix (last updated 2026-08-26)

- Spec story 47 (retire `gh-stars.py` and the `github-stars` skill once
  ghstars is stable) has no ticket. Ticket 14 explicitly punts on the
  retirement mechanism. Spec.md's Further Notes calls retirement "a
  follow-up action," but that line sits outside the formal Out of Scope
  section, so nothing tracks the actual retirement work. Open a ticket for
  it once ticket 14 lands.

### Open

"Ready" means the ticket is speced and workable once its blockers clear,
not that it's unblocked — check the Blocked-by column.

| #  | Ticket                                                  | Status                                      | Blocked by                    |
| -- | ------------------------------------------------------- | ------------------------------------------- | ----------------------------- |
| 12 | Nudges                                                  | ready-for-agent — unblocked                 | none                          |
| 13 | Packaging & distribution (Linux)                        | ready-for-agent — blocked                   | 9, 10, 11, 12, 14            |
| 14 | Accompanying agent skill (replaces github-stars)        | ready-for-agent — blocked                   | 4, 5, 6, 7, 10, 11, 12       |
| 15 | Windows & macOS release binaries                        | ready-for-agent — blocked                   | 13                            |
| 18 | Distinguish "cleared" from "never classified"          | needs design — deferred                     | 5, 6, 7, 8, 9, 10, 11, 12, 14 |
| 23 | In-TUI config editor                                    | ready-for-agent — unblocked                 | none                          |
| 24 | Chrome, live state, and an explicit sync key            | ready-for-agent — unblocked                 | none                          |
| 25 | View mode switcher and Folder view                      | ready-for-agent — unblocked                 | none                          |
| 26 | Grid view mode                                          | ready-for-agent — blocked                   | 25                            |
| 27 | Finding and ordering Stars: filters, search, sort       | partial — Folder integration blocked | 25                            |
| 28 | Colour system for Lists and Categories                  | ready-for-agent — unblocked                 | none                          |

**Unblocked frontier:** 12, 23, 24, 25, 28. Ticket 27 has implemented
flat-view filters, search, sorting, and persistence. Ticket 25 still blocks
Folder integration.

### Follow-ups queued by the user

- Add License to the Star DetailPane and Filter. The local snapshot did not
  store License before ticket 27 work; the sync model now fetches it.
- Add an explicit TUI sync key after ticket 27. The key must never start sync
  automatically. Show progress, completion, and error states in the TUI.

### New TUI defect to ticket (queued by user, 2026-08-26)

Star-list ("repo list") view: pressing the select key on a row should flip
its `[ ]` mark to `[x]`, but the mark instead goes blank/vanishes. Reported
as specific to the star-list table — not reproduced in the List/Category
picker screens used for tagging (`table.add_columns("List", "Intent",
"Category", "Visibility"[, "Items"])`, `tui/app.py:216,297`), which have no
"Sel" column at all and aren't a toggle-select surface — you drill into a
List there, you don't multi-select rows. **Caution:** that picker is
probably what's being called "folder mode" in the report, not an actual
Folder view — ticket 25 (Folder view) is not implemented yet (`grep -i
folder src/ghstars/tui/` finds nothing), so re-confirm the repro against
the real running TUI before assuming a genuine list-vs-folder inconsistency.

Investigated by inspection (`action_toggle_select` at `tui/app.py:658`, `_refresh_table` at `:593`),
`action_toggle_select`/`_refresh_table`): the underlying data path looks
correct — a `run_test()` pilot repro confirms `table.get_cell(row, "sel")`
returns `"[x]"` after pressing the select key, and `DataTable.update_cell()`
(Textual 8.2.8) calls `self.refresh()` internally, so this isn't an obvious
missing-repaint bug at the code level. The vanishing is likely a real
terminal-rendering artifact (bracket characters, cell justification, or
row-height/cursor-highlight interaction) that only shows up in an actual
running TUI, not in a headless pilot test. Needs a live repro (`ghstars
tui`, arrow to a row, press the select key, watch the cell) before ticketing
a fix — no ticket number assigned yet.

## TUI UI overhaul (tickets 20-29)

Speced and ticketed 2026-08-18. Summary — see the references below for
detail:

- Design source: `.scratch/ghstars-v1/spec.md` stories 50-72 and
  `CONTEXT.md` (`View Mode`,
  `Folder`, `Filter` added; `Category`'s old "Topic except in Reference
  Lists" carve-out removed).
- ADR 0006 (accepted) supersedes ADR 0003: the TUI syncs only on an
  explicit keypress. ADR 0005 (proposed, do not build against it yet):
  compound Category, e.g. `Explore: Dev Tools / AI`.
- TUI performance measurements that justified postponing pagination are
  recorded in `.scratch/ghstars-v1/spec.md`'s Out of Scope section (line
  248) — do not re-measure.
- ADRs 0001 and 0002's `Implemented` values are recorded in
  `docs/adr/INDEX.md` (`done` and `in-progress`).

## Current state

Local dev state (`~/.ghstars/state/stars.json`/`lists.json`) is
live-synced against the real account (pradyumnac; last verified count:
1551 stars, 8 Lists, 2026-08-26 — re-check before relying on it) — safe to run `ghstars sync`/`list`/`lists`/`tag`
against it again.

## Dev flow & review process

Picking up the next ticket batch:

1. Compute the frontier — tickets whose blockers are all `done`, per each
   ticket file's `Status:` line (cross-check against the Task rail table
   above, which mirrors it).
2. Launch one fresh (non-fork) `general-purpose` agent per frontier ticket,
   in a single message, each with `isolation: "worktree"`. Give each a
   self-contained prompt: ticket path, relevant spec sections, existing code
   map, scope boundaries against sibling tickets running concurrently, and
   any known collision files.
3. **Ticket-scoped review**: each agent runs `/code-review` on its own diff
   and applies fixes autonomously — no need to check back with the user
   unless a finding is a genuine design decision, not a code-quality one.
4. Supervisor reviews each agent's diff, merges its worktree branch into
   `main` (resolve conflicts by hand, never by discarding either side),
   updates the ticket file's `Status:`/`## Comments`, and updates this Task
   rail table + harness `TaskList` — every round, not batched up for later.
5. Once every ticket in a layer is merged, run one **whole-project review**:
   a fresh advisor agent reviews overall project health. **Report-only** —
   surface findings to the user, do not auto-apply fixes from this pass.
6. Clean up: `git worktree remove` + `git branch -d` a merged ticket's
   worktree once its merge commit is confirmed on `main` — these aren't
   auto-cleaned and accumulate as clutter otherwise.

Operational notes:

- A worktree agent that hits a background session/API limit mid-task fails
  with a `status: failed` task notification, but its worktree and partial
  diff survive — resume it with `SendMessage` to its `agentId` (not a fresh
  agent) and it picks up with full context.
- Real, state-changing GitHub mutations (unstar, list create/update,
  rename/drain) must never be invoked for real during development/testing —
  see "Live-testing constraints" below.

## Live-testing constraints on the `gh` account (pradyumnac)

- Token scopes: `repo`, `user`, `admin:public_key`, `gist`, `read:org`.
- **`remove_star` (real unstar mutation) must never be invoked for real
  outside a human-confirmed, deliberate test.**
- A leftover real test List (`zzz-ghstars-verify-delete-me`, id
  `UL_kwDOABkiBM4AhnTU`) still exists on the real account. `delete_list()`
  exists in `core/github_client.py` (abstract, with fake + real impls)
  since ticket 07, but no `ghstars` command exposes it yet — delete the List manually via github.com, or wire up a
  command first.

## `docs/explanation/known-limitations.md` — what's already documented

Sync isn't an atomic snapshot; sync always re-fetches everything (no
incremental path); pending tag pushes aren't batched. Don't rediscover
these.
