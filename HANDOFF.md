# Handoff

Context from work sessions that does not live anywhere else yet. Everything
here is either an undecided question, a finding whose only record is a
commit message or a conversation, or a gap noticed while working that's out
of scope to fix right now.

Delete a section once it lands in `TODO.md`, an ADR, `AGENTS.md`, or
`README.md` — this file is a staging area, not a second source of truth.

## Audit findings — landed (2026-08-17)

The spec/issues consistency audit and its solutioning follow-up (both run
2026-08-17) are landed as **ticket 17**
(`.scratch/ghstars-v1/issues/17-audit-findings-mid-term-fixes.md`), which
bundles all four findings/proposals as one ticket's scope of work per user
direction, rather than the solutioning pass's original suggestion of two
new tickets (17/18) plus direct amends to 07/10/13. Ticket 17 is
self-contained (states its own design rationale and open questions in its
`## Comments`) — no need to keep the original findings/proposals text here.
Being implemented next; see the Task rail below.

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

**Note (2026-08-17 session): harness task IDs below do NOT equal ticket
numbers this round** — task IDs 1-3 were the audit/solutioning agents and
ticket 05, in that order; ticket 17's implementation is task #4. Listed
here by ticket number regardless, per the mirroring convention; see
harness `TaskList` for actual task IDs/owners if resuming these specific
runs.

| # | Ticket | Status | Blocked by |
|---|---|---|---|
| 1 | Core scaffolding, fake client, state store, CLI skeleton | done | — |
| 2 | Real GitHub client — fetch stars | done | 1 |
| 3 | Fetch Lists & parse taxonomy | done | 2 |
| 4 | Local tagging & two-way sync push | done | 3 |
| 5 | Three-way merge & Retriage Queue | done — merged to `main` (`e48b704`) | 4 |
| 6 | Unstar detection & Archived state | done | 2 |
| 7 | Category rename & drain | pending — 17 will edit this file's Blocked-by/AC, not implement it | 4 (17 will add 5) |
| 8 | Agent-mode status command & verify | pending | 3, 5 |
| 9 | TUI tagging/bulk-tag/retag | pending — held, see below | 4 |
| 10 | Export engine | pending — 17 will add an AC to this file | 3 |
| 11 | State diff | pending — held, see below | 4 |
| 12 | Nudges | pending | 8 |
| 13 | Packaging & distribution (Linux) | pending — 17 will add 14 to Blocked-by | 5, 6, 7, 8, 9, 10, 11, 12 |
| 14 | Accompanying agent skill (replaces github-stars) | pending | 4, 5, 6, 7, 8, 10, 11, 12 |
| 15 | Windows & macOS release binaries | pending | 13 |
| 16 | Push a tag edit immediately, like unstar already does | pending — held, see below | 4, 5 (lifted) |
| 17 | Mid-term bug fixes from the audit (Explore:General default, Intent exclusivity, 07/10/13 doc edits) | **in progress** (harness task #4, worktree agent) | 5 |

**Ticket 05: done**, merged to `main` at `e48b704` (2026-08-17), see prior
session notes below for the full verification trail. Ticket 16's hard-block
on 05 is lifted (noted in its file), but 16 itself is still held per the
plan below.

**Ticket 17: in progress**, launched 2026-08-17 as a worktree agent,
bundling all four audit findings/proposals as one ticket's scope per user
direction — see `.scratch/ghstars-v1/issues/17-audit-findings-mid-term-fixes.md`
for the full scope and design rationale.

**07/09/10/11/16 remain held** until ticket 17 lands — per the
audit-findings-workflow gate
(`~/.claude/projects/-home-doe-repos-ghstars/memory/feedback_audit_findings_workflow.md`).
Ticket 17 itself touches 07/10/13's *files* (dependency/AC edits only,
not implementation), which is why those three show a "17 will edit"
note above rather than being fully held.

## Current state

Tickets 01/02/03/04/06 are done, committed, and pushed to `main` on
`pradyumnac/ghstars` (public GitHub repo — renamed from an unrelated old
private Go repo of the same name, which now lives at
`pradyumnac/ghstars-go-archived`). **Ticket 05 is done and merged to local
`main` (`e48b704`) but not yet pushed to `origin`** — local main is 1
commit ahead of `origin/main` as of this session; push it before starting
work in a new session/worktree off `origin/main` or it'll be missing this
ticket. 96 tests pass, `mise run check` is clean.
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

## Sequencing strategy for the 5/7/9/10/11 frontier (decided 2026-08-17)

**05 solo first, then 07/09/10/11 in parallel.** Reasoning, from reading all
five ticket files this session:

- **05** restructures `core/sync.py`'s control flow itself (push moves from
  unconditional-at-start to conditional-after-fetch). Any other ticket
  touching that file concurrently would be editing code mid-restructure —
  worth avoiding even though nothing else in the frontier *should* need to
  touch `sync.py`'s push logic.
- **07** (category rename/drain) touches `core/lists.py`-equivalent + CLI +
  the GitHub client's list-mutation calls — direct API mutations (rename,
  bulk membership migration), not the `pending_list_ids` staging path 05
  restructures. Low file overlap with 05.
- **09** (TUI) is a new, mostly self-contained module — a thin wrapper
  calling into `ghstars.core`, no core logic changes. Lowest risk.
- **10** (export engine) is a new, config-driven module — reads
  stars/lists, writes files. No core mutation path at all.
- **11** (state diff) wraps `git diff`/`git log -p` against `state/` —
  entirely new, no core changes, explicitly forbidden from touching git
  init/commit behavior.

07/09/10/11 have negligible file overlap with each other (list-mutation
CLI, TUI, export, diff are four separate concerns) — once 05 lands, run
them as one parallel worktree-agent layer, same pattern as the 03+06 round
(see "Parallel-agent orchestration pattern" below): launch all four in one
message, each told upfront what the others are touching so a real
collision (if one turns up) gets handled by keeping diffs additive rather
than avoided by scope-shrinking.

**Review discipline for this layer** (per "Review process" above): each of
05/07/09/10/11 gets its own ticket-scoped `/code-review` with autonomous
fixes as it lands. After 07/09/10/11 all land (05 already reviewed solo
before they start), run one report-only whole-project review over the
combined layer — same as was done after 03+06.

**Why 05 first, not just "some ticket first":** it fixes a real
conflict-clobbering bug live in shipped code today (low actual risk solo,
since this GitHub account is the only writer right now, but worth closing
before more write paths accumulate) and unblocks ticket 16's design
question, which cannot be scoped until 05's merge logic exists to call
synchronously from `tag`.
