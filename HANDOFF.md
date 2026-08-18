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

Tickets 1-7, 9-11, 16, 17, and 19 are done and merged to `main` — see
each ticket's own `Status:`/`## Comments` for details.

Status column below is taken verbatim (or near-verbatim) from each ticket
file's own `Status:` line, reconciled 2026-08-17 — the previous version of
this table used "pending" loosely for several tickets whose files actually
already say `ready-for-agent`; that mismatch is fixed here. "Ready" only
means the ticket is speced and workable once its blockers clear, not that
it's unblocked — check the Blocked-by column too.

| #  | Ticket                                                    | Status                                                          | Blocked by                    |
| -- | ------------------------------------------------------------ | -------------------------------------------------------------------- | ------------------------------ |
| 8  | Agent-mode status command & verify                        | **ready-for-agent — unblocked, pick up next**                  | 3, 5, 19 (all done)            |
| 12 | Nudges                                                    | ready-for-agent — blocked                                      | 8                              |
| 13 | Packaging & distribution (Linux)                          | ready-for-agent — blocked                                      | 5, 6, 7, 8, 9, 10, 11, 12, 14  |
| 14 | Accompanying agent skill (replaces github-stars)          | **ticket file has no `Status:` line** — add one before picking up | 4, 5, 6, 7, 8, 10, 11, 12      |
| 15 | Windows & macOS release binaries                          | ready-for-agent — blocked                                      | 13                             |
| 18 | Distinguish "cleared on GitHub" from "never classified"   | needs design, not yet speced — no acceptance criteria yet — deliberately deferred until 05-12, 14 done | 5, 6, 7, 8, 9, 10, 11, 12, 14 |

## TUI UI overhaul — speced 2026-08-18, not yet ticketed

A grilling session settled the TUI's navigation, presentation, and config
design. Written up already:

- `spec.md` stories 50-72, replacing the old "TUI visual/interaction design
  left to implementation" non-goal.
- `CONTEXT.md` — `Category` no longer has the "Topic except in Reference
  Lists" carve-out (it gave one slot two names). Added `View Mode`, `Folder`,
  `Filter`.
- ADR 0004 (accepted) supersedes ADR 0003: the TUI can sync on an explicit
  keypress, never on its own initiative.
- ADR 0005 (proposed, do not build against it): compound Category splitting a
  kind from a subject, e.g. `Explore: Dev Tools / AI`. Direction chosen,
  mechanism open.

**Next step: convert stories 50-72 into ticket files.** The user asked for
this as a separate step, after the spec landed. Scope it as two tickets, not
one — config and keybindings first, because the rest reads config.

### Two defects found while speccing, both live on `main`

- `tui/app.py:432` — `_fetch_rate_limit` catches only `GitHubApiError`. A
  `ValidationError` from `RateLimitResponse.model_validate` is not wrapped by
  `_graphql`, so it escapes the worker and leaves the rate-limit bar blank
  forever with no notification. `_apply_tag` catches broadly for exactly this
  reason and documents why; the two workers disagree. Spec story 63 covers
  the fix.
- `RateLimitBar` is constructed with no initial content, so it paints as a
  blank strip for the ~0.7s `check_rate_limit()` takes. This is why the bar
  looks absent on launch. Spec story 72 covers it.

### Measurements — do not redo these

TUI performance was measured on the real 1530-Star account before deciding on
pagination: `load_stars()` 32ms, building 1530 `DataTable` rows 52ms, full
`clear()`+rebuild 56ms, one `update_cell` 0.1ms, `check_rate_limit()` 0.69s.
The TUI is not slow at this scale; the only slow thing is the network call.
Pagination is postponed, not rejected — see the spec's Out of Scope.

### Deferred, with an owner

- Immediate push of a tag edit — stays ticket 16. `tag_star()` still only
  stages `pending_list_ids` (`core/tagging.py:101`); the user's recollection
  that this had already changed is wrong, and `git log` on that file confirms
  nothing has changed since ticket 19.
- Compound Category — ADR 0005, plus its own issue and spec entry.

### Needs your confirmation

ADRs 0001 and 0002 predated the `adr-lifecycle` format (no `# NNNN — Title`,
no `## Status`), so `build_index.py` skipped both and `INDEX.md` silently
omitted two binding decisions. Structure added, reasoning untouched. The
`Implemented` values are inferred from code, not stated by the user: 0001
`done` (three-way merge and Retriage Queue exist), 0002 `in-progress`
(`config/` and `state/` exist, `runtime/` does not until ticket 12). Confirm
or correct both.

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
incremental path); pending tag pushes and default-classification pushes
aren't batched. Don't rediscover these.
