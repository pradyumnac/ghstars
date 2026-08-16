# Handoff

Context from work sessions that does not live anywhere else yet. Everything
here is either an undecided question, a finding whose only record is a
commit message or a conversation, or a gap noticed while working that's out
of scope to fix right now.

Delete a section once it lands in `TODO.md`, an ADR, `AGENTS.md`, or
`README.md` — this file is a staging area, not a second source of truth.

## Start next session with: spec/issues consistency audit

Run an independent advisor review (fresh agent, no shared context —
same pattern as this session's whole-project reviews) over
`.scratch/ghstars-v1/spec.md` together with the full
`.scratch/ghstars-v1/issues/*.md` ticket list. Look for inconsistencies
between them and any observations worth surfacing — e.g. spec sections
that no ticket covers, ticket scope that's drifted from what the spec
says, acceptance criteria that no longer match a decision made in a
later ticket's `## Comments` (ticket 04 and 05 already have one such
cross-reference — the push-then-pull ordering — that a consistency
pass should confirm is still accurate once 05 actually lands).

Checked (2026-08-16): no `mattpocock-skills` skill is purpose-built for
this. `/domain-modeling` is vocabulary/term-level only;
`/improve-codebase-architecture` is code-architecture, not spec/ticket
content. This is the generic advisor pattern, not a named skill — spawn
it directly rather than searching for a skill to wrap it in. Report
findings only; this is exactly the report-only whole-project-review
class of check per the project's review-process convention (see the
"Review process" section elsewhere in this file), so don't auto-apply
fixes from it without checking back first.

## Task rail

Mirror of the session-scoped Task tool (`TaskCreate`/`TaskUpdate`/
`TaskList`/`TaskGet`) — see the `handoff` skill's "Task rail reconciliation"
and "Task rail mirroring" sections for the read/write rules. Always present,
even empty: a missing section looks identical to "nothing active," which
hides the difference between "no plan" and "forgot to mirror one."

Mirrors `.scratch/ghstars-v1/issues/*.md`, ticket-for-ticket (task ID N ==
ticket `NN`). The ticket files are the actual source of truth (acceptance
criteria, `## Comments` with implementation notes); this table is a status
snapshot only.

| # | Ticket | Status | Blocked by |
|---|---|---|---|
| 1 | Core scaffolding, fake client, state store, CLI skeleton | done | — |
| 2 | Real GitHub client — fetch stars | done | 1 |
| 3 | Fetch Lists & parse taxonomy | done | 2 |
| 4 | Local tagging & two-way sync push | done | 3 |
| 5 | Three-way merge & Retriage Queue | **pending — frontier** | 4 |
| 6 | Unstar detection & Archived state | done | 2 |
| 7 | Category rename & drain | **pending — frontier** | 4 |
| 8 | Agent-mode status command & verify | pending | 3, 5 |
| 9 | TUI tagging/bulk-tag/retag | **pending — frontier** | 4 |
| 10 | Export engine | **pending — frontier** | 3 |
| 11 | State diff | **pending — frontier** | 4 |
| 12 | Nudges | pending | 8 |
| 13 | Packaging & distribution (Linux) | pending | 5, 6, 7, 8, 9, 10, 11, 12 |
| 14 | Accompanying agent skill (replaces github-stars) | pending | 4, 5, 6, 7, 8, 10, 11, 12 |
| 15 | Windows & macOS release binaries | pending | 13 |
| 16 | Push a tag edit immediately, like unstar already does | pending | 4, 5 |

Frontier right now: **5, 7, 9, 10, 11** — all unblocked, ready to grab. 16 is
also nominally unblocked-by-count but hard-gated on 5's design landing first
(see below).

## Current state

Tickets 01/02/03/04/06 are done, committed, and **pushed to `main`** on
`pradyumnac/ghstars` (public GitHub repo — renamed from an unrelated old
private Go repo of the same name, which now lives at
`pradyumnac/ghstars-go-archived`). 85 tests pass, `mise run check` is clean.
Local dev state (`~/.ghstars/state/stars.json`/`lists.json`) is live-synced
against the real account (pradyumnac, 1530 stars, 7 Lists as of this
session) — safe to run `ghstars sync`/`list`/`lists`/`tag` against it again.

## Two things ticket 05 must know before starting

Both are written into `.scratch/ghstars-v1/issues/05-three-way-merge-retriage-queue.md`'s
`## Comments`, but they're easy to miss on a skim, so repeating here:

1. **`sync()`'s push step is unconditional today — 05 has to restructure it, not layer on top.** `core/sync.py`'s `_push_pending_list_membership()` pushes every `Star.pending_list_ids` edit *before* `fetch_stars()`/`fetch_lists()` run in that same sync call — nothing is compared against current GitHub state first. A concurrent conflicting GitHub-side edit is silently clobbered right now, not "GitHub wins" as ticket 05 requires. 05 needs to move the push to *after* the fresh fetch and make it conditional on the three-way merge outcome (push / no-op / Retriage).
2. **Ticket 16 exists and is deliberately blocked on 05.** It asks whether `ghstars tag` should push immediately (like `ghstars unstar` already does) instead of staging `pending_list_ids` for the next sync. Analysis this session found `unstar` doesn't have the "wait for conflict arbitration" problem at all — it's the Star-existence axis (ticket 06), never subject to 05's List-membership merge. `tag` is the only write command that needs a second `ghstars sync` to take effect. 16 can't be safely designed until 05's merge logic exists to run synchronously inside `tag` itself.

## Review process (from project memory, not yet in any committed doc)

- **Ticket-scoped review**: run `/code-review` on the ticket's own diff, apply
  fixes autonomously (self-directed, no need to check back with the user
  unless a finding is a genuine design decision, not a code-quality one).
- **Whole-project review**: once per completed *layer* (a batch of parallel
  tickets), after they're all merged — a fresh advisor agent reviews overall
  project health. **Report-only**: surface findings to the user, do not
  auto-apply fixes from this pass.
- Keep the Task rail (harness `TaskList`) updated at the end of every round,
  not batched up for later.

This convention lives in this session's memory files
(`~/.claude/projects/-home-doe-repos-ghstars/memory/feedback_two_stage_code_review.md`
and `project_ghstars_ticket_workflow.md`), not in any file inside the repo —
worth promoting into `AGENTS.md` or `docs/agents/` if it keeps proving out.

## Parallel-agent orchestration pattern (used once, for tickets 03+06)

Two fresh (non-`fork`) `general-purpose` agents, each in an isolated
`isolation: "worktree"`, launched in one message. Both were told upfront they
might collide on `core/sync.py` (03 adds List-fetching, 06 adds the
archived-diff) and to keep that file's diff minimal/additive rather than
avoid the collision. Merged sequentially afterward by hand — real conflicts
in `sync.py`, `cli/__init__.py`, `core/__init__.py`, `github/client.py`,
`github/schema.py`, all resolved by combining both sides' additions (nothing
was actually incompatible, just concurrent). One process slip from that
round worth remembering: a broad `git add -A` briefly committed the two
agent worktree directories as embedded git repos — caught and fixed
(`.claude/worktrees/` is now gitignored).

## Live-testing constraints on the `gh` account (pradyumnac)

- Token scopes as of this session's end: `repo`, `user`, `admin:public_key`,
  `gist`, `read:org` — the `user` scope (needed for `createUserList`/
  `updateUserListsForItem`) was granted mid-session; earlier tickets'
  "blocked by scope" notes in `.scratch/ghstars-v1/issues/04-*.md` predate
  that and are now stale in that one respect (the file itself was updated
  once the scope landed and the live test re-run — see its `## Comments`).
- **`remove_star` (real unstar mutation) must never be invoked for real
  outside a human-confirmed, deliberate test** — it's a visible, not fully
  reversible action against the real account's star list. This constraint
  was set explicitly for ticket 06 and should carry into any future ticket
  touching it (e.g. ticket 07's list mutations don't touch stars directly,
  but be deliberate about any new real mutation).
- `create_list`/`update_list_membership_for_item` (the `tag` push path) ARE
  now verified live and safe to exercise again — a real test List
  (`zzz-ghstars-verify-delete-me`, id `UL_kwDOABkiBM4AhnTU`) still exists on
  the real account from this session's verification and has no `ghstars`
  command to delete it yet (`delete_list` is ticket 07). Delete it manually
  via github.com if it's cluttering the real Lists view.

## `docs/explanation/known-limitations.md` — what's already documented

Three limitations are written up there in detail already; don't rediscover
them:

1. **Sync isn't an atomic snapshot** — `fetch_stars()`/`fetch_lists()` are
   two separate calls, so a repo starred+listed in the gap can show up in
   `lists.json` with no matching `stars.json` record. Self-heals next sync;
   `reconcile_list_membership()` skips unmatched items rather than erroring.
2. **Sync always re-fetches everything, no incremental path** — measured
   cost on the real account: **~27 API points per sync** (steady state,
   nothing changed), **+2 points per pending tag push**. Against the
   5000/hour budget this isn't a practical problem today, but it's a fixed
   cost regardless of change size.
3. **Pending tag pushes aren't batched** — N pending tags cost 2N sequential
   `gh api graphql` calls in one sync (resolve node ID + mutation, per
   star), no GraphQL alias batching used.

## Next steps

Frontier is **5, 7, 9, 10, 11** (all unblocked). Given the two findings
above, **05 first** is the strong recommendation — it unblocks 16's design
question and fixes the conflict-handling gap that's silently present in the
shipped code today (low real risk solo, since this account is the only
writer right now, but worth closing before more write paths accumulate).
