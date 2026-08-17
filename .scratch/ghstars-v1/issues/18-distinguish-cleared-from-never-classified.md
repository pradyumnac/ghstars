# 18 — Distinguish "cleared on GitHub" from "never classified"

**What to build:** a way to tell apart two Star states that look identical today — empty `list_ids` — but mean different things:

1. A Star genuinely never classified by anyone (ticket 17's intended target for the `Explore: General` default).
2. A Star that *was* classified, but had its List membership cleared directly on github.com, outside `ghstars` (no local pending edit staged, no `ghstars` command involved).

Local state has no signal to distinguish these today, so case 2 currently gets silently swept into case 1 and defaulted into `Explore: General` on the next sync — potentially overwriting the user's deliberate choice to clear it.

**Not a bug in ticket 17** — ticket 17's `_apply_default_classification` (spec story 4) does exactly what its own acceptance criteria specified ("any star ... whose `list_ids` is still empty ... is assigned"). This ticket exists to add the missing state tracking (e.g. a tombstone, or an explicit "last classified at" marker) that would let a future version of that function tell the two cases apart, if the user decides the distinction is worth the added state.

**Deliberately deferred — this is edge-case cleanup, not core v1 functionality.** Do not pick this up, or let it block/execute, until the main v1 flow is implemented. Mirrors ticket 13's own "all v1-functional pieces must be in place" gate for the same reason.

**Blocked by:** 05, 06, 07, 08, 09, 10, 11, 12, 14.

**Status:** needs design, not yet speced — no acceptance criteria yet. Write these once the main flow lands and the user decides whether this distinction is worth new state, and if so, what shape that state takes (a tombstone record? a `last_classified_at` timestamp compared against sync history? something else?).

## Comments (originating finding, 2026-08-17)

From ticket 17's post-implementation Comments, verbatim:

> A star whose List membership was cleared by the user directly on
> github.com (no local pending edit staged) is indistinguishable from
> "genuinely never classified" from local state alone, and will also
> get defaulted into `Explore: General`. The ticket's own Scope 1 text
> states the assignment rule unconditionally ("any star ... whose
> `list_ids` is still empty ... is assigned"), with no carve-out for
> this case, and there is no local signal today that could tell the
> two apart.

Confirmed independently by the supervisor while reviewing ticket 17's
merge — a real, narrow edge case, not a design flaw in ticket 17
itself. Filed here so it has a home, deliberately deferred rather than
reopening ticket 17 or blocking the main flow on a design question
that doesn't need answering yet.
