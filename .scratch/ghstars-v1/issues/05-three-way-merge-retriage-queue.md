# 05 — Three-way merge & Retriage Queue

**What to build:** Conflict handling for the **List-membership axis** — a Star's Intent/Category classification changing on GitHub and locally since the last sync, distinct from the Star-existence axis (unstar/Archived) covered in 06. Three-way merge per Star, per sync: base (last-synced snapshot) vs. current GitHub state vs. pending local edits. Only one side changed → apply it. Both sides changed to the same result → no-op. Both sides changed to different results → GitHub wins unconditionally; the local pending edit is never applied and never silently dropped — it's written to the local-only Retriage Queue (never a GitHub List) for the user to revisit. No auto-merge/union logic, ever.

**Blocked by:** 04.

**Status:** done

- [x] All four merge scenarios implemented: local-only change, remote-only change, both-same (no-op), both-different (conflict)
- [x] On conflict, GitHub's state wins and is applied; the losing local edit is never applied
- [x] The losing local edit is written to the Retriage Queue, never discarded
- [x] Retriage Queue is local-only — never synced to GitHub, never a `UserList`
- [x] `ghstars retriage --json` lists queue contents
- [x] No auto-merge/union of conflicting classifications anywhere in the path
- [x] `sync()`'s push step is restructured to run the three-way comparison *before* deciding to push (see Comments) — the current ticket-04 push-then-pull order must change, this doesn't just layer on top of it

## Comments (pre-implementation, from ticket 04's wrap-up analysis)

Ticket 04's `_push_pending_list_membership()` currently pushes every
pending edit **unconditionally**, at the very start of `sync()`, before
`fetch_stars()`/`fetch_lists()` ever run in that same call. That was a
deliberate but incomplete placeholder — the code comment says pushing
is deferred to sync time "so a concurrent GitHub-side change has
something to be checked against," but nothing in ticket 04 actually
checks anything. It just pushes blindly, then pulls fresh state
afterward and lets `reconcile_list_membership()` overwrite `list_ids`
from that fresh pull. A concurrent conflicting GitHub-side edit is
silently clobbered today, not "GitHub wins" as this ticket requires.

This ticket needs to move the push to *after* the fresh
`fetch_stars()`/`fetch_lists()` (so "current GitHub state" is actually
known), diff it against the last-synced base and the pending edit, and
only call `update_list_membership_for_item` when the merge says to —
routing conflicts to the Retriage Queue instead of pushing. This is a
restructuring of `sync()`'s control flow, not an additive change on
top of ticket 04's current order.

## Comments (post-implementation, 2026-08-17)

Implemented as a worktree agent, merged to `main` at `e48b704`. `sync()`
now runs `_merge_pending_list_membership()` after
`fetch_stars()`/`fetch_lists()`/`reconcile_list_membership()`, diffing
`previous.list_ids` (base) against fresh `star.list_ids` (remote) and
`previous.pending_list_ids` (local) per star. The Retriage Queue write
(`state/retriage.json`, via new `StateStore.load_retriage`/`save_retriage`)
is ordered *before* `stars.json`/`lists.json` so a crash between writes
never loses a losing edit's record — worst case is a harmless duplicate
entry re-detected next sync. `ghstars retriage --json` added, reusing the
existing `_render_records` CLI helper.

Ticket-scoped `/code-review` ran and found two real issues, both fixed:
the retriage-durability ordering above, and a duplicated self-healing
load pattern (extracted to a shared `_load_self_healing[T]` helper). One
thing flagged but deliberately left alone: `_load_self_healing` reuses the
pre-existing bare-comma `except OSError, json.JSONDecodeError,
ValidationError:` style from `_load_previous_stars` — valid on this
project's Python 3.14 (PEP 758), not a bug; kept for in-file consistency
rather than unilaterally introducing a second exception-clause style.

Two tests from ticket 04 (`test_sync_pushes_a_pending_edit_before_pulling`,
`test_sync_isolates_a_pending_push_failure_and_reports_it`) encoded the
old push-before-fetch semantics and were rewritten to match the new
correct behavior; a new test covers a genuine push failure (List deleted
on GitHub concurrently) so that coverage isn't lost. `mise run check`:
96/96 tests, fmt/lint/mypy clean — verified independently by the
supervisor both pre- and post-merge.
