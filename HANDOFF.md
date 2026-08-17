# Handoff

Context from work sessions that does not live anywhere else yet. Everything
here is either an undecided question, a finding whose only record is a
commit message or a conversation, or a gap noticed while working that's out
of scope to fix right now.

Delete a section once it lands in `TODO.md`, an ADR, `AGENTS.md`, or
`README.md` — this file is a staging area, not a second source of truth.

## In progress: 07/09/10/11 parallel layer

Local `main` was already pushed and matched `origin/main` at the start of
this session (confirmed via `git status` — nothing to do there). User chose
the parallel-layer option: tickets 07, 09, 10, and 11 are being implemented
concurrently, each in its own isolated worktree agent, each running its own
ticket-scoped `/code-review` (autonomous fixes) before merge. Once all four
are merged and `mise run check` is green, run one report-only whole-project
advisor review over the combined layer (harness task #5), per "Review
process" below. See "Task rail" for live status and harness task IDs.

## Sync must always be intentful — never auto-triggered

Explicit user direction (surfaced mid-session, during the 07/09/10/11
layer): once the product is ready, the TUI, CLI, and the agent skill (ticket
14) must never auto-pull or auto-sync GitHub state on their own. Every
surface always serves from local state (`~/.ghstars/state/`); a real GitHub
fetch happens only when the user explicitly runs `ghstars sync` (or
equivalent explicit action), never as a side effect of opening the TUI,
running an unrelated command, or an agent skill invocation.

Not to be fixed in-place right now — user was explicit: don't touch
already-running tasks (07 was still in a worktree agent when this came up).
If the upcoming whole-project advisor review (harness task #5) finds a
violation (e.g. `ghstars tui` or `ghstars export` calling `sync()` on
startup), it goes through the confirmation gate and becomes a **new
ticket**, not an in-session fix — same discipline as ticket 18. The advisor
review has also been given this as an explicit check item, plus a secondary
goal of general codebase-architecture improvement suggestions (report-only,
per "Review process" below).

**Two-round plan, per explicit user direction**: harness task #5 (whole-
project advisor review) runs first, over the merged 07/09/10/11 layer.
Once #5 lands, run a **second, dedicated** advisor round (harness task #6,
blocked by #5) specifically deep-diving these two asks — sync-intentionality
verification and architecture-improvement suggestions — rather than treating
them as just bullet items inside #5's general pass.

**Task #5 result (done)**: report-only, no files touched. Part 1 (project
health): merge-conflict resolutions verified clean (AST-diffed imports/
`__all__`), no bugs, coverage thorough. Part 2.1 (sync-intentfulness audit):
**one finding, needs user confirmation before becoming a ticket** —
`src/ghstars/tui/app.py:236-242` (`on_mount`) unconditionally calls
`check_rate_limit()` (a real `gh api graphql` call) the instant `ghstars
tui` launches, no user action required. It's read-only rate-limit metadata
(no Star/List data pulled, nothing written to `state/`), and ticket 09's
own spec/tests call for it explicitly — but it still fails the letter of
"real GitHub fetch only via explicit `ghstars sync`." Everything else
audited clean: `category rename`/`drain`'s fresh-fetch is confirmed as the
narrow ticket-17 exception, not a creeping pattern; TUI tag/bulk-tag/retag
only fire on explicit keypress; `diff`/`export` never touch `GitHubClient`.
Part 2.2 (architecture, exploratory): `cli/__init__.py` at 532 lines,
consider splitting into `cli/commands/*.py` before tickets 13/14 add more;
`sync.py::_apply_pushed_membership` and `category.py::_apply_membership_diff`
are near-duplicate List-membership-mirroring logic, worth a shared helper;
the "fetch fresh, skip diverged" pattern is independently implemented twice
within `category.py`; `tag_star()`'s per-call `fetch_lists()` cost will
compound as more callers (TUI, future ticket 14) appear; `GitHubClient`'s
single `_graphql()` chokepoint is a good seam to mechanically enforce the
no-auto-sync guarantee later (e.g. a call-counter assertion in tests).

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
equal ticket numbers**: harness task #1 = ticket 07, #2 = ticket 09, #3 =
ticket 10, #4 = ticket 11, #5 = whole-project advisor review (blocked by
1-4) — check harness `TaskList` for live status if resuming.

| #   | Ticket                                                                                              | Status                                                                                                  | Blocked by                    |
| --- | --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | ----------------------------- |
| 1   | Core scaffolding, fake client, state store, CLI skeleton                                            | done                                                                                                    | —                             |
| 2   | Real GitHub client — fetch stars                                                                    | done                                                                                                    | 1                             |
| 3   | Fetch Lists & parse taxonomy                                                                        | done                                                                                                    | 2                             |
| 4   | Local tagging & two-way sync push                                                                   | done                                                                                                    | 3                             |
| 5   | Three-way merge & Retriage Queue                                                                    | done — merged to `main` (`e48b704`), confirmed pushed to `origin/main`                                  | 4                             |
| 6   | Unstar detection & Archived state                                                                   | done                                                                                                    | 2                             |
| 7   | Category rename & drain                                                                             | **done — merged to `main` (`4edd4e3`), `mise run check` green (197 tests)**                             | 4, 5                          |
| 8   | Agent-mode status command & verify                                                                  | pending                                                                                                 | 3, 5                          |
| 9   | TUI tagging/bulk-tag/retag                                                                          | **done — merged to `main` (`b04dba2`), `mise run check` green (157 tests)**                             | 4                             |
| 10  | Export engine                                                                                       | **done — merged to `main` (`d768410`), `mise run check` green (145 tests)**                             | 3                             |
| 11  | State diff                                                                                          | **done — merged to `main` (`6d8005a`), `mise run check` green (118 tests)**                             | 4                             |
| 12  | Nudges                                                                                              | pending                                                                                                 | 8                             |
| 13  | Packaging & distribution (Linux)                                                                    | pending                                                                                                 | 5, 6, 7, 8, 9, 10, 11, 12, 14 |
| 14  | Accompanying agent skill (replaces github-stars)                                                    | pending                                                                                                 | 4, 5, 6, 7, 8, 10, 11, 12     |
| 15  | Windows & macOS release binaries                                                                    | pending                                                                                                 | 13                            |
| 16  | Push a tag edit immediately, like unstar already does                                               | pending — hold lifted now that 17 merged; not yet started                                               | 4, 5 (lifted)                 |
| 17  | Mid-term bug fixes from the audit (Explore:General default, Intent exclusivity, 07/10/13 doc edits) | **done — merged to `main` (`4363a9b`)**                                                                 | 5                             |
| 18  | Distinguish "cleared on GitHub" from "never classified" (edge case surfaced during 17's review)     | filed, needs design — **deliberately deferred, do not pick up until the main flow (05-12, 14) is done** | 5, 6, 7, 8, 9, 10, 11, 12, 14 |

## Current state

Local dev state (`~/.ghstars/state/stars.json`/`lists.json`) is
live-synced against the real account (pradyumnac, 1530 stars, 7 Lists as
of the last live sync) — safe to run `ghstars sync`/`list`/`lists`/`tag`
against it again.

## Review process (from project memory, not yet in any committed doc)

- **Ticket-scoped review**: run `/code-review` on the ticket's own diff, apply
  fixes autonomously (self-directed, no need to check back with the user
  unless a finding is a genuine design decision, not a code-quality one).
- **Whole-project review**: once per completed _layer_ (a batch of parallel
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

## Live-testing constraints on the `gh` account (pradyumnac)

- Token scopes as of this session's end: `repo`, `user`, `admin:public_key`,
  `gist`, `read:org`.
- **`remove_star` (real unstar mutation) must never be invoked for real
  outside a human-confirmed, deliberate test**
- `create_list`/`update_list_membership_for_item` (the `tag` push path) are
  verified live and safe to exercise again — a real test List
  (`zzz-ghstars-verify-delete-me`, id `UL_kwDOABkiBM4AhnTU`) still exists
  on the real account and has no `ghstars` command to delete it yet
  (`delete_list` is ticket 07). Delete it manually via github.com if it's
  cluttering the real Lists view — still unresolved as of this session.

## `docs/explanation/known-limitations.md` — what's already documented

1. **Sync isn't an atomic snapshot**
2. **Sync always re-fetches everything, no incremental path**
3. **Pending tag pushes aren't batched**
4. **Default-classification pushes aren't batched either** (added by
   ticket 17) — same sequential-cost shape as #3, mostly matters once, on
   a first sync against an account with many pre-existing unclassified
   stars.

## Sequencing strategy for the 7/9/10/11 frontier (decided 2026-08-17, partly superseded)

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
