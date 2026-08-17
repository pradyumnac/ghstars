# Handoff

Context from work sessions that does not live anywhere else yet. Everything
here is either an undecided question, a finding whose only record is a
commit message or a conversation, or a gap noticed while working that's out
of scope to fix right now.

Delete a section once it lands in `TODO.md`, an ADR, `AGENTS.md`, or
`README.md` — this file is a staging area, not a second source of truth.

## Spec/issues consistency audit — findings, awaiting triage (2026-08-17)

**Status: done, unactioned.** Advisor agent (fresh, no shared context)
completed a report-only pass over `.scratch/ghstars-v1/spec.md` and all 16
`issues/*.md` files. Per convention, nothing below was auto-applied — land
each item into its real home (a ticket's acceptance criteria/Comments,
`docs/`, or a new ticket) once triaged, then delete it from this list.

1. **Real gap — spec story 4 ("`Explore: General` default") has no owning
   ticket.** Ticket 03 explicitly punts its matching checkbox to 04; ticket
   04 (done) never picked it up — no acceptance criterion, no Comments
   claim, and `grep -rn "General" src/` confirms no auto-assignment code
   exists anywhere. New stars are never defaulted into `Explore: General`.
2. **Real gap — spec story 16 (Intent mutual exclusivity) is unenforced and
   unowned.** Spec + CONTEXT.md both require a Star sit in exactly one of
   Explore/Current/Retired per Category at a time. No ticket (checked 03,
   04, 05, 07, 09) enforces it, and `tagging.py`'s `tag_star()` just appends
   to `pending_list_ids` — never removes a conflicting sibling variant.
3. **Confirmed still accurate, needs a re-check on merge** — the 04/05
   push-then-pull cross-reference. Ticket 05 hadn't landed at audit time
   (still `ready-for-agent`, worktree agent was mid-run); `sync.py` still
   does the unconditional push exactly as 05's Comments describe. **Re-run
   this specific check once ticket 05's worktree branch merges to `main`**
   — that's the point it could actually go stale.
4. **Worth flagging before picking up 07** — ticket 07 (category drain)
   does bulk List-membership migration but is only `Blocked by: 04`, not
   05, even though ticket 16's own Comments establish that any
   List-membership write bypassing 05's synchronous three-way merge risks
   "reintroducing the blind-overwrite problem 05 exists to fix." Not a flat
   contradiction (07 doesn't say which path drain uses) — but worth a
   decision when 07 starts: route `drain` through the same merge-aware path
   05 builds, or accept it's a different (admin-initiated, less
   conflict-prone) mutation and document why it's exempt.
5. **Minor drift** — ticket 13 (release gate) isn't blocked by ticket 14
   (agent skill), despite spec's Further Notes calling the skill "a real
   deliverable... shipped alongside ghstars." Possibly intentional (skill
   doesn't block a package release) but inconsistent with the spec's
   framing.
6. **Minor, formally ungoverned** — spec story 39 (`config/` never
   auto-committed) has no ticket-level criterion anywhere (unlike `state/`,
   covered by ticket 11). `~/.ghstars/config/` scaffolding landed via an
   out-of-ticket commit (`0fe4180`) whose own message admits "no ticket has
   defined config/'s schema." Satisfied vacuously today, not by design.
7. **Not new, still open** — ticket 03's CONTEXT.md question (whether a
   colon-containing General List name like `"Notes: Misc"` needs an escape
   hatch from the malformed-name heuristic) is still unresolved; already
   correctly parked there for a `/domain-modeling` pass.
8. **Minor** — spec story 23 (malformed names shouldn't silently break
   export) isn't addressed in ticket 10's acceptance criteria. Ticket 03
   covers the sync-side flagging; ticket 10 says nothing about how export
   handles a malformed List name. Likely fine by construction, not explicit.

No dangling story-number references anywhere in the tickets, and no ticket
contradicts itself internally.

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
numbers this round** — task #1 is the audit (not a ticket), task #2 is
ticket 05. Listed here by ticket number regardless, per the mirroring
convention; see harness `TaskList` for actual task IDs/owners if resuming
these specific runs.

| # | Ticket | Status | Blocked by |
|---|---|---|---|
| 1 | Core scaffolding, fake client, state store, CLI skeleton | done | — |
| 2 | Real GitHub client — fetch stars | done | 1 |
| 3 | Fetch Lists & parse taxonomy | done | 2 |
| 4 | Local tagging & two-way sync push | done | 3 |
| 5 | Three-way merge & Retriage Queue | done — merged to `main` (`e48b704`) | 4 |
| 6 | Unstar detection & Archived state | done | 2 |
| 7 | Category rename & drain | pending — frontier after 5 lands | 4 |
| 8 | Agent-mode status command & verify | pending | 3, 5 |
| 9 | TUI tagging/bulk-tag/retag | pending — frontier after 5 lands | 4 |
| 10 | Export engine | pending — frontier after 5 lands | 3 |
| 11 | State diff | pending — frontier after 5 lands | 4 |
| 12 | Nudges | pending | 8 |
| 13 | Packaging & distribution (Linux) | pending | 5, 6, 7, 8, 9, 10, 11, 12 |
| 14 | Accompanying agent skill (replaces github-stars) | pending | 4, 5, 6, 7, 8, 10, 11, 12 |
| 15 | Windows & macOS release binaries | pending | 13 |
| 16 | Push a tag edit immediately, like unstar already does | pending | 4, 5 |
| — | Spec/issues consistency audit (not a ticket) | done — findings awaiting triage, see section above | — |

**Ticket 05: done.** Implemented in a worktree agent, ticket-scoped
`/code-review` applied (2 real fixes, 1 deliberate no-op — see the ticket
file's post-implementation Comments), independently re-verified by the
supervisor (read the merge logic, confirmed the ADR 0001 citation is real,
`mise run check` green pre- and post-merge), fast-forward merged to `main`
at `e48b704` after explicit user confirmation (2026-08-17). Ticket 16's
hard-block on 05 is now lifted (noted in its file), but 16 itself is not
being picked up yet — see below.

**Plan changed 2026-08-17, after the audit findings came back** (see the
findings section above) — the previous plan to move straight to a
7/9/10/11 parallel layer once 05 landed is now on **hold**. New sequence,
per explicit user instruction:

1. ~~Wait for ticket 05's worktree agent to finish, then wait for the user
   to confirm it's resolved~~ — done, see above.
2. Launch a **second advisor agent**, scoped to *solutioning*, not
   findings — research spec.md/issues/codebase and propose best-practice,
   clean-code solutions for the audit's identified issues (story 4
   default, story 16 mutual exclusivity, and the other findings above).
   **Propose-only — it must not implement anything.** Returns proposals;
   the user takes them up one at a time. **This is the next step.**
3. **Do not launch 07/09/10/11/16 (or any other frontier ticket) in
   parallel until the audit-derived fixes are resolved.** The "Sequencing
   strategy" section below still describes the *file-overlap* reasoning
   for why 07/09/10/11 can run together once that layer starts — it's just
   gated later than originally planned.

See `~/.claude/projects/-home-doe-repos-ghstars/memory/feedback_audit_findings_workflow.md`
for the full reasoning behind this gate.

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
