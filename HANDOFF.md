# Handoff

Context from work sessions that does not live anywhere else yet. Everything
here is either an undecided question, a finding whose only record is a
commit message or a conversation, or a gap noticed while working that's out
of scope to fix right now.

Delete a section once it lands in `TODO.md`, an ADR, `AGENTS.md`, or
`README.md` — this file is a staging area, not a second source of truth.

## Start next session with: ticket 07 (category rename & drain)

Explicit user direction to end this session: pick back up on ticket 07
("renaming") next session. Ticket 17 is merged and closed out (see Task
rail below) — 07's `Blocked by` (04, 05) is fully satisfied, its file
already carries the fresh-state-check acceptance criterion 17 added, and
nothing is holding it back. The previously-planned option of running
07/09/10/11 together as one parallel layer (see "Sequencing strategy"
below) is still valid background context, but the user's explicit
instruction was to pick up 07 specifically — start there, and decide fresh
next session whether 09/10/11 join in parallel or come later.

Before starting: push local `main` to `origin` (see "Current state" below
for exactly what's pending), and read ticket 07's file in full — its new
"fetch fresh state, skip-and-report diverged Stars" acceptance criterion
(added by ticket 17) is a real design constraint, not boilerplate.

## Task rail

Mirror of the session-scoped Task tool (`TaskCreate`/`TaskUpdate`/
`TaskList`/`TaskGet`) — see the `handoff` skill's "Task rail reconciliation"
and "Task rail mirroring" sections for the read/write rules. Always present,
even empty: a missing section looks identical to "nothing active," which
hides the difference between "no plan" and "forgot to mirror one."

Mirrors `.scratch/ghstars-v1/issues/*.md`, ticket-for-ticket (task ID N ==
ticket `NN`) where possible. The ticket files are the actual source of
truth (acceptance criteria, `## Comments` with implementation notes); this
table is a status snapshot only. **This session's harness task IDs do not
equal ticket numbers** (tasks 1-3 were the audit/solutioning agents and
ticket 05; ticket 17 is task #4; ticket 18 is task #5, filed not worked) —
check harness `TaskList` for actual IDs if resuming a specific run.

| # | Ticket | Status | Blocked by |
|---|---|---|---|
| 1 | Core scaffolding, fake client, state store, CLI skeleton | done | — |
| 2 | Real GitHub client — fetch stars | done | 1 |
| 3 | Fetch Lists & parse taxonomy | done | 2 |
| 4 | Local tagging & two-way sync push | done | 3 |
| 5 | Three-way merge & Retriage Queue | done — merged to `main` (`e48b704`), confirmed pushed to `origin/main` | 4 |
| 6 | Unstar detection & Archived state | done | 2 |
| 7 | Category rename & drain | **pending — pick up first next session**, per explicit user direction | 4, 5 |
| 8 | Agent-mode status command & verify | pending | 3, 5 |
| 9 | TUI tagging/bulk-tag/retag | pending — hold lifted now that 17 merged; not yet started | 4 |
| 10 | Export engine | pending — hold lifted now that 17 merged; not yet started | 3 |
| 11 | State diff | pending — hold lifted now that 17 merged; not yet started | 4 |
| 12 | Nudges | pending | 8 |
| 13 | Packaging & distribution (Linux) | pending | 5, 6, 7, 8, 9, 10, 11, 12, 14 |
| 14 | Accompanying agent skill (replaces github-stars) | pending | 4, 5, 6, 7, 8, 10, 11, 12 |
| 15 | Windows & macOS release binaries | pending | 13 |
| 16 | Push a tag edit immediately, like unstar already does | pending — hold lifted now that 17 merged; not yet started | 4, 5 (lifted) |
| 17 | Mid-term bug fixes from the audit (Explore:General default, Intent exclusivity, 07/10/13 doc edits) | **done — merged to `main` (`4363a9b`)** | 5 |
| 18 | Distinguish "cleared on GitHub" from "never classified" (edge case surfaced during 17's review) | filed, needs design — **deliberately deferred, do not pick up until the main flow (05-12, 14) is done** | 5, 6, 7, 8, 9, 10, 11, 12, 14 |

**Ticket 17: done.** Implemented in worktree agent `a232ee952e488d4f7`
(resumed once after hitting a session limit mid-fix). All 4 scopes
complete; ticket-scoped `/code-review` found and fixed 4 real issues
(excluding failed/conflicted stars from default-classification, guarding
`create_list` against exceptions, batching the List update, and an STE
writing-style fix); independently re-verified by the supervisor (read
`sync.py`/`tagging.py`/`cli` diffs in full, confirmed the exclusion logic
and batching are correct). Committed (`22a0686`) and merged to `main`
(`4363a9b`) after explicit user confirmation; `mise run check` re-verified
green on `main` post-merge (109/109 tests). Worktree cleaned up (removed +
branch deleted). One genuine edge case surfaced during review — filed as
ticket 18 rather than silently fixed or ignored, per explicit user
instruction to give it a home without letting it block the main flow.

**The audit-findings-workflow hold on 07/09/10/11/16 is now lifted** —
ticket 17 merged. Per explicit user direction, next session starts with
07 specifically, not the full parallel layer (see "Start next session
with" above).

## Current state

Confirmed via `git reflog show origin/main`: `origin/main` is at `def85d1`
— tickets 01-06 **and** ticket 05's merge (`e48b704`) plus this session's
HANDOFF/ticket-17-filing commits through `def85d1` are all already live on
`pradyumnac/ghstars` (public GitHub repo — renamed from an unrelated old
private Go repo of the same name, now at `pradyumnac/ghstars-go-archived`).
That push happened during this session but was **not** run by the
assistant — noting it here since it wasn't an explicitly confirmed action,
unlike every other push/merge this session. Local `main` is now 4 commits
ahead of `origin/main` (`c07107b` ticket-18 filing, `b70b571` HANDOFF
wrap-up, `22a0686` ticket 17's implementation, `4363a9b` its merge commit)
— none of this is pushed yet. Push it before starting ticket 07 next
session, or `origin/main` will be missing ticket 17's work (05 is already
confirmed pushed) and misleading if anyone else looks at the GitHub repo.

109 tests pass on `main` as of this session's end. `mise run check` is
clean.

Local dev state (`~/.ghstars/state/stars.json`/`lists.json`) is
live-synced against the real account (pradyumnac, 1530 stars, 7 Lists as
of the last live sync) — safe to run `ghstars sync`/`list`/`lists`/`tag`
against it again.

**Worktree hygiene, done this session:** four fully-merged worktrees
(tickets 05 and 17, plus two orphaned leftovers from the 03+06 round
predating this session) were unlocked/removed and their branches deleted
— they were pure disk clutter, already captured in `main`'s history via
the merge commits. `git worktree list` is clean (just the main worktree)
as of this session's end. Repeat this cleanup pass whenever a
worktree-agent ticket merges — don't let it accumulate again.

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
(`~/.claude/projects/-home-doe-repos-ghstars/memory/feedback_two_stage_code_review.md`,
`project_ghstars_ticket_workflow.md`, and now also
`feedback_audit_findings_workflow.md` for the confirmation-gate/solutioning
variant used this session), not in any file inside the repo — worth
promoting into `AGENTS.md` or `docs/agents/` if it keeps proving out.

## Parallel-agent orchestration pattern (used for tickets 03+06, then solo for 05 and 17)

Fresh (non-`fork`) `general-purpose` agents, each in an isolated
`isolation: "worktree"`. For a true parallel batch (03+06): launch all in
one message, told upfront what files they might collide on and to keep
diffs additive rather than avoid the collision — merge conflicts get
resolved by the supervisor afterward, by hand, combining both sides.
For a solo ticket with a real risk of hitting a background session/API
limit mid-task (05, 17 this session): the agent can be resumed via
`SendMessage` to its `agentId` after a `failed` task-notification — its
worktree and partial diff survive the failure, so resuming picks up
exactly where it left off rather than restarting.

One process slip from the original 03+06 round, still worth remembering:
a broad `git add -A` briefly committed the two agent worktree directories
as embedded git repos — caught and fixed (`.claude/worktrees/` is
gitignored). Newer learning from this session: **worktrees for merged
tickets are not auto-cleaned** — `git worktree remove` + `git branch -d`
them once their merge commit is confirmed on `main`, ideally the same
session, or they silently accumulate (three were found stale this
session, one dating back to before this session started).

## Live-testing constraints on the `gh` account (pradyumnac)

- Token scopes as of this session's end: `repo`, `user`, `admin:public_key`,
  `gist`, `read:org`.
- **`remove_star` (real unstar mutation) must never be invoked for real
  outside a human-confirmed, deliberate test** — it's a visible, not fully
  reversible action against the real account's star list. This constraint
  was set explicitly for ticket 06 and carries into any future ticket
  touching it (e.g. ticket 07's list mutations don't touch stars directly,
  but be deliberate about any new real mutation).
- `create_list`/`update_list_membership_for_item` (the `tag` push path) are
  verified live and safe to exercise again — a real test List
  (`zzz-ghstars-verify-delete-me`, id `UL_kwDOABkiBM4AhnTU`) still exists
  on the real account and has no `ghstars` command to delete it yet
  (`delete_list` is ticket 07). Delete it manually via github.com if it's
  cluttering the real Lists view — still unresolved as of this session.

## `docs/explanation/known-limitations.md` — what's already documented

Four limitations are written up there in detail already; don't rediscover
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
4. **Default-classification pushes aren't batched either** (added by
   ticket 17) — same sequential-cost shape as #3, mostly matters once, on
   a first sync against an account with many pre-existing unclassified
   stars.

## Sequencing strategy for the 7/9/10/11 frontier (decided 2026-08-17, partly superseded)

**Originally decided:** 05 solo, then 17 solo (audit-derived fixes), then
07/09/10/11 as one parallel layer once 17 merges. **Superseded at
session-end**: 17 has merged, but the explicit user instruction was to
pick up 07 alone next session (see "Start next session with" at the top),
not the full four-ticket parallel layer. The file-overlap reasoning below
is still accurate background if/when 09/10/11 do get picked up alongside
or after 07 — just no longer the committed plan for what happens
immediately next.

- **07** (category rename/drain) touches CLI + the GitHub client's
  list-mutation calls directly — not the `pending_list_ids` staging path
  05/17 touch. Low file overlap.
- **09** (TUI) is a new, mostly self-contained module — a thin wrapper
  calling into `ghstars.core`, no core logic changes. Lowest risk.
- **10** (export engine) is a new, config-driven module — reads
  stars/lists, writes files. No core mutation path at all.
- **11** (state diff) wraps `git diff`/`git log -p` against `state/` —
  entirely new, no core changes, explicitly forbidden from touching git
  init/commit behavior.

07/09/10/11 have negligible file overlap with each other — once ticket 17
merges, run them as one parallel worktree-agent layer, same pattern as the
03+06 round (see "Parallel-agent orchestration pattern" above): launch all
four in one message, each told upfront what the others are touching.

**Review discipline for this layer** (per "Review process" above): each of
07/09/10/11 gets its own ticket-scoped `/code-review` with autonomous
fixes as it lands. After all four land, run one report-only whole-project
review over the combined layer — same as was done after 03+06.

**16 stays held too**, even though its ticket-level `Blocked by` (4, 5) is
already satisfied — its design still depends on 17's fixes being settled
first, per the audit-findings-workflow gate.
