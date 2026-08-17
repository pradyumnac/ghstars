# 0004 — Pending-tag staging and the Retriage Queue stay in place, dormant, after ticket 16

## Status

accepted

## Implemented

done

## Context

Ticket 04 built `Star.pending_list_ids`: `ghstars tag` staged its edit
locally, and `sync()` pushed it. Ticket 05 built `_merge_pending_list_membership`
and the Retriage Queue (`RetriageEntry`, `ghstars retriage`) to arbitrate that
staged edit against concurrent GitHub-side changes, three-way, at the next
sync — GitHub wins unconditionally on a real conflict; the losing local edit
goes to the Retriage Queue, never applied, never discarded.

Ticket 16 changes `ghstars tag` (and, since it shares `core.tagging.tag_star()`,
every TUI tag/retag/bulk-tag path too) to push immediately instead: it computes
the desired List-membership set from a fresh `fetch_lists()` call already made
at tag-time, and if that shows the local snapshot has drifted from GitHub's
current state, it names the diverged List(s) and blocks outright rather than
staging or auto-resolving anything. `tag_star()` was the only code path in the
whole codebase that ever wrote `pending_list_ids` (verified by grep across
`src/ghstars`). Once ticket 16 lands, nothing produces a pending edit anymore,
so `_merge_pending_list_membership`'s pending-edit branch, `RetriageEntry`, and
`ghstars retriage` become unreachable in normal operation — not broken, just
never triggered.

## Decision

Leave `pending_list_ids`, `_merge_pending_list_membership`, `RetriageEntry`,
and `ghstars retriage` in place, unmodified, as part of ticket 16 — do not
delete them just because their current sole producer stopped producing. They
remain available as ready-built conflict-arbitration infrastructure for a
future feature that might reintroduce a deferred/staged edit (e.g. an offline
mode, or a deliberate batch-tag command that intentionally defers pushes
instead of pushing per-item).

## Consequences

- A future reader who finds `_merge_pending_list_membership`, `RetriageEntry`,
  or `ghstars retriage` with no live call site producing their input should
  not assume it is dead/abandoned code and delete or "fix" it without
  checking this ADR first.
- Ticket 05's existing tests keep exercising this path directly (calling
  `_merge_pending_list_membership` and friends in isolation), even though no
  real `ghstars tag` call reaches it anymore after ticket 16. That is
  intentional — it keeps the mechanism verified in case it is reactivated.
- `ghstars retriage` remains a real CLI command whose queue will, in normal
  post-ticket-16 operation, stay empty. If that proves confusing in practice,
  a doc note (not a code change) is the fix.
- If a future ticket reintroduces a `pending_list_ids` producer, this ADR
  should be updated (or superseded) to record the new trigger.

## Alternatives considered

- **Remove `pending_list_ids`, `_merge_pending_list_membership`,
  `RetriageEntry`, and `ghstars retriage` as part of ticket 16** — rejected.
  No concrete near-term feature needs them today, but they are exactly the
  three-way conflict-arbitration logic a future deferred/offline write path
  would otherwise have to re-derive from scratch. Keeping them costs only
  inert code and continued test upkeep, judged cheaper than rebuilding this
  later.
