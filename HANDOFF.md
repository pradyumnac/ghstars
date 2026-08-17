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
