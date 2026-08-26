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

- Issue 01 — core scaffolding, fake client, state store: complete.
- Issue 02 — real GitHub client, fetch stars: complete.
- Issue 03 — fetch Lists, parse taxonomy: complete.
- Issue 04 — local tagging, two-way sync push: complete.
- Issue 05 — three-way merge, Retriage Queue: complete.
- Issue 06 — unstar detection, archived state: complete.
- Issue 07 — category rename/drain: complete.
- Issue 09 — TUI tagging, bulk tagging, retagging: complete.
- Issue 10 — export engine: complete.
- Issue 11 — state diff: complete.
- Issue 16 — lightweight push (immediate tag push): complete.
- Issue 17 — audit findings, mid-term fixes: complete.
- Issue 19 — architecture cleanup, post-layer: complete.
- Issue 08 — agent-mode status command & verify: complete.
- Issue 20 — fix TUI rate-limit-bar defects: complete.
- Issue 21 — TUI config foundation: tui.toml and tui-state.toml: complete.
- Issue 22 — TUI detail pane: complete.

See each ticket file's own `Status:`/`## Comments` for implementation
detail. Reconciled against the ticket files directly on 2026-08-26.

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

| #  | Ticket                                                    | Status                                                          | Blocked by                    |
| -- | ------------------------------------------------------------ | -------------------------------------------------------------------- | ------------------------------ |
| 12 | Nudges                                                    | ready-for-agent — unblocked                                    | none                           |
| 13 | Packaging & distribution (Linux)                          | ready-for-agent — blocked                                      | 9, 10, 11, 12, 14              |
| 14 | Accompanying agent skill (replaces github-stars)          | ready-for-agent — blocked                                      | 4, 5, 6, 7, 10, 11, 12         |
| 15 | Windows & macOS release binaries                          | ready-for-agent — blocked                                      | 13                             |
| 18 | Distinguish "cleared on GitHub" from "never classified"   | needs design, not yet speced — no acceptance criteria yet — deliberately deferred until 05-12, 14 done | 5, 6, 7, 8, 9, 10, 11, 12, 14 |
| 23 | In-TUI config editor                                      | ready-for-agent — unblocked                                    | none                           |
| 24 | Chrome, live state, and an explicit sync key              | ready-for-agent — unblocked                                    | none                           |
| 25 | View mode switcher and Folder view                        | ready-for-agent — unblocked                                    | none                           |
| 26 | Grid view mode                                            | ready-for-agent — blocked                                      | 25                             |
| 27 | Finding and ordering Stars: filters, search, sort         | ready-for-agent — blocked                                      | 25                             |
| 28 | Colour system for Lists and Categories                    | ready-for-agent — unblocked                                    | none                           |
| 29 | Open in browser, and unstar with confirmation             | ready-for-agent — unblocked                                    | none                           |

**Next batch to start (queued by user, 2026-08-26):** 12, 23, 25, 28, 29 — all
unblocked per the table above.

### New TUI defect to ticket (queued by user, 2026-08-26)

Star-list ("repo list") view: pressing the select key on a row should flip
its `[ ]` mark to `[x]`, but the mark instead goes blank/vanishes. Reported
as specific to the star-list table — not reproduced in the List/Category
picker screens used for tagging (`table.add_columns("List", "Intent",
"Category", "Visibility"[, "Items"])`, `tui/app.py:197,251`), which have no
"Sel" column at all and aren't a toggle-select surface — you drill into a
List there, you don't multi-select rows. **Caution:** that picker is
probably what's being called "folder mode" in the report, not an actual
Folder view — ticket 25 (Folder view) is not implemented yet (`grep -i
folder src/ghstars/tui/` finds nothing), so re-confirm the repro against
the real running TUI before assuming a genuine list-vs-folder inconsistency.

Investigated by inspection (`tui/app.py:558-570`,
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

### Detail pane — already implemented (ticket 22, answering a question queued 2026-08-26)

Yes — `DetailPane` (`tui/app.py:92`, wired at line 356). It's not a
separate mode you switch into: it's a panel that's always visible and
auto-refreshes to show whatever star the cursor is currently on, via
`on_data_table_row_highlighted` → `_refresh_detail_pane()` (`tui/app.py:522-538`).
No keybinding needed — just move the cursor (arrow keys) over the star
table and the pane updates.

## TUI UI overhaul (tickets 20-29)

Speced and ticketed 2026-08-18. Summary — see the references below for
detail:

- Design source: `spec.md` stories 50-72 and `CONTEXT.md` (`View Mode`,
  `Folder`, `Filter` added; `Category`'s old "Topic except in Reference
  Lists" carve-out removed).
- ADR 0006 (accepted) supersedes ADR 0003: the TUI syncs only on an
  explicit keypress. ADR 0005 (proposed, do not build against it yet):
  compound Category, e.g. `Explore: Dev Tools / AI`.
- Two known defects on `main`, both covered by spec stories: the
  rate-limit worker's narrow exception catch (`tui/app.py:432`, story 63)
  and `RateLimitBar`'s blank paint on launch (story 72).
- TUI performance measurements that justified postponing pagination are
  recorded in `spec.md`'s Out of Scope section (near line 248) — do not
  re-measure.
- ADRs 0001 and 0002's `Implemented` values are recorded in
  `docs/adr/INDEX.md` (`done` and `in-progress`).

Tickets 20, 21, and 22 have no blockers and can start in parallel. Ticket
29 first extracts `unstar_cmd`'s lock-load-archive-save sequence into
`ghstars.core` (a prefactor step), so the CLI and TUI share it the way
`tag_star()` already is shared.

## Current state

Local dev state (`~/.ghstars/state/stars.json`/`lists.json`) is
live-synced against the real account (pradyumnac, 1530 stars, 7 Lists as
of the last live sync) — safe to run `ghstars sync`/`list`/`lists`/`tag`
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
  exists in `core/category.py` since ticket 07, but no `ghstars` command
  exposes it yet — delete the List manually via github.com, or wire up a
  command first.

## `docs/explanation/known-limitations.md` — what's already documented

Sync isn't an atomic snapshot; sync always re-fetches everything (no
incremental path); pending tag pushes aren't batched. Don't rediscover
these.
