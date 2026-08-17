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
table is a status snapshot only. The 07/09/10/11 parallel layer is fully
done as of this session: harness tasks #1-4 (tickets 07/09/10/11) all
merged to `main`; task #5 (whole-project advisor review) completed and its
findings are resolved — see "Architecture-improvement suggestions" below
for the one open item; task #6 (a planned second advisor round) was
cancelled by explicit user direction as redundant with #5's depth. Check
harness `TaskList` for live status if resuming with new tasks in flight.

| #   | Ticket                                                                                              | Status                                                                                                  | Blocked by                    |
| --- | --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | ----------------------------- |
| 1   | Core scaffolding, fake client, state store, CLI skeleton                                            | done                                                                                                    | —                             |
| 2   | Real GitHub client — fetch stars                                                                    | done                                                                                                    | 1                             |
| 3   | Fetch Lists & parse taxonomy                                                                        | done                                                                                                    | 2                             |
| 4   | Local tagging & two-way sync push                                                                   | done                                                                                                    | 3                             |
| 5   | Three-way merge & Retriage Queue                                                                    | done — merged to `main` (`e48b704`), confirmed pushed to `origin/main`                                  | 4                             |
| 6   | Unstar detection & Archived state                                                                   | done                                                                                                    | 2                             |
| 7   | Category rename & drain                                                                             | **done — merged to `main` (`4edd4e3`), `mise run check` green (197 tests)**                             | 4, 5                          |
| 8   | Agent-mode status command & verify                                                                  | pending — **gated on 19**, per explicit user direction                                                 | 3, 5, 19                      |
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
| 19  | Architecture cleanup from the 07/09/10/11 advisor review                                            | **ready-for-agent — do this before 08, per explicit user direction**                                    | none                          |

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

## Architecture-improvement suggestions — landed

The exploratory findings from the 2026-08-17 whole-project advisor review
(over the merged 07/09/10/11 layer) landed as
[ticket 19](.scratch/ghstars-v1/issues/19-architecture-cleanup-post-layer.md),
per explicit user direction to file them as a new ticket, gated to run
**before ticket 08** (ticket 08's `Blocked by` now includes 19 — see Task
rail above). The sync-intentionality check from the same review landed as
[ADR 0003](docs/adr/0003-github-sync-is-always-explicit.md) — the one
finding (`ghstars tui`'s automatic `check_rate_limit()` on launch) was
confirmed by the user as an acceptable, documented exception, not a
violation.
