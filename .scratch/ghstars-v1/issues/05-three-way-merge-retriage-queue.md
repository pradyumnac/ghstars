# 05 — Three-way merge & Retriage Queue

**What to build:** Conflict handling for the **List-membership axis** — a Star's Intent/Category classification changing on GitHub and locally since the last sync, distinct from the Star-existence axis (unstar/Archived) covered in 06. Three-way merge per Star, per sync: base (last-synced snapshot) vs. current GitHub state vs. pending local edits. Only one side changed → apply it. Both sides changed to the same result → no-op. Both sides changed to different results → GitHub wins unconditionally; the local pending edit is never applied and never silently dropped — it's written to the local-only Retriage Queue (never a GitHub List) for the user to revisit. No auto-merge/union logic, ever.

**Blocked by:** 04.

**Status:** ready-for-agent

- [ ] All four merge scenarios implemented: local-only change, remote-only change, both-same (no-op), both-different (conflict)
- [ ] On conflict, GitHub's state wins and is applied; the losing local edit is never applied
- [ ] The losing local edit is written to the Retriage Queue, never discarded
- [ ] Retriage Queue is local-only — never synced to GitHub, never a `UserList`
- [ ] `ghstars retriage --json` lists queue contents
- [ ] No auto-merge/union of conflicting classifications anywhere in the path
- [ ] `sync()`'s push step is restructured to run the three-way comparison *before* deciding to push (see Comments) — the current ticket-04 push-then-pull order must change, this doesn't just layer on top of it

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
