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

Tickets 1-7, 9-11, 17, and 19 are done and merged to `main` — see each
ticket's own `Status:`/`## Comments` for details.

| #  | Ticket                                                            | Status                                                       | Blocked by                    |
| -- | ------------------------------------------------------------------ | -------------------------------------------------------------- | ------------------------------ |
| 8  | Agent-mode status command & verify                                | **ready — unblocked, pick up next**                           | 3, 5, 19                      |
| 12 | Nudges                                                            | pending                                                        | 8                              |
| 13 | Packaging & distribution (Linux)                                  | pending                                                        | 5, 6, 7, 8, 9, 10, 11, 12, 14  |
| 14 | Accompanying agent skill (replaces github-stars)                  | pending                                                        | 4, 5, 6, 7, 8, 10, 11, 12      |
| 15 | Windows & macOS release binaries                                  | pending                                                        | 13                             |
| 16 | Push a tag edit immediately, like unstar already does             | pending — hold lifted                                          | 4, 5                           |
| 18 | Distinguish "cleared on GitHub" from "never classified"           | filed, needs design — deliberately deferred until 05-12, 14 done | 5, 6, 7, 8, 9, 10, 11, 12, 14 |

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
`project_ghstars_ticket_workflow.md`, `feedback_audit_findings_workflow.md`),
not in any file inside the repo — worth promoting into `AGENTS.md` or
`docs/agents/` if it keeps proving out.

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
