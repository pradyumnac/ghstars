# 17 — Mid-term bug fixes from the spec/issues consistency audit

**What to build:** four fixes bundled together, all originating from the 2026-08-17 spec/issues consistency audit and its follow-up solutioning pass (see `HANDOFF.md`'s now-superseded "Spec/issues consistency audit" and "Solutioning proposals" sections for full traceability — this ticket is the landing place for both, replacing them as the source of truth going forward):

1. Implement the `Explore: General` default classification (spec story 4) — currently unimplemented anywhere in the codebase.
2. Enforce Intent mutual exclusivity (spec story 16) — currently unenforced in `tag_star()`.
3. Gate ticket 07 (category rename & drain) on ticket 05, with a fresh-state-check safety rule.
4. Three minor doc/ticket fixes: ticket 13's dependency on 14, a `config/` governance note, and a ticket 10 acceptance criterion for malformed List names.

**Blocked by:** 05 (done, merged `e48b704`).

**Status:** done

## Scope 1 — `Explore: General` default classification

- [x] Inside `sync()` (`core/sync.py`), after `_merge_pending_list_membership()` returns and before the retriage/save block: any non-archived star whose `list_ids` is still empty at that point is assigned to `Explore: General`.
- [x] `Explore: General` List is looked up in the already-fetched `lists`; created on GitHub (public, per story 48) only if it doesn't exist yet — lazy, not eager, and idempotent across syncs.
- [x] The membership push for a newly-defaulted star is a direct full-replace call (nothing else to preserve on an empty `list_ids`) — **not** routed through ticket 05's three-way merge. A synthetic default has no staged local edit or remote opinion to reconcile against, so conflict arbitration doesn't apply here.
- [x] Per-star push failures are isolated (same pattern as `_merge_pending_list_membership`'s `except Exception`) and reported back (e.g. a `failed_default_pushes`-shaped field on `SyncResult`), never fatal to the whole sync.

## Scope 2 — Intent mutual exclusivity

- [x] `tag_star()` (`core/tagging.py`): when the target List's intent is Explore, Current, or Retired, strip any id already in `pending_list_ids` that belongs to a sibling List of the *same Category* and a *different* one of those three lifecycle Intents, before appending the new List's id.
- [x] Auto-resolve, not a hard error — spec story 17 (move a Star from `Current` to `Retired` via a single `tag` call, without unstarring) requires this to just work, not require a manual untag first.
- [x] `tag_star()`'s return communicates what (if anything) was removed — extend its return shape (e.g. a small `TagResult` alongside the existing `Star`, matching `SyncResult`'s pattern) — and `tag_cmd` (`cli/__init__.py`) reports it in both plain-text and `--json` output, not silently.
- [x] `Reference`-intent Lists and unprefixed General Lists (`intent=None`) are exempt from exclusivity — never treated as a conflict candidate, never stripped.

## Scope 3 — Gate ticket 07 on ticket 05

- [x] Edit `.scratch/ghstars-v1/issues/07-category-rename-drain.md`: change `Blocked by: 04` to `Blocked by: 04, 05`.
- [x] Add a new acceptance criterion to ticket 07: `drain`/`rename` fetch fresh GitHub state before computing/writing the bulk change, and **skip and report** (never silently overwrite) any Star whose live List membership has already diverged from what triggered the migration.
- [x] This ticket (17) only edits ticket 07's file — it does not implement `category rename`/`category drain` themselves; that's still ticket 07's job, now correctly scoped.

## Scope 4 — Minor doc/ticket fixes

- [x] `.scratch/ghstars-v1/issues/13-*.md`: add `14` to its `Blocked by:` list.
- [x] `docs/adr/0002-*.md` or `docs/explanation/known-limitations.md`: add a short note documenting that `~/.ghstars/config/` scaffolding (introduced by commit `0fe4180`) is one-time, idempotent, and never git-auto-committed — giving that ad-hoc commit a documented owner.
- [x] `.scratch/ghstars-v1/issues/10-*.md`: add an acceptance criterion — export skips and reports a malformed List rather than exporting it under a guessed Intent/Category.

## Comments (pre-implementation, from the audit's solutioning pass, 2026-08-17)

**Scope 1 design rationale:** an empty-`list_ids` star at the point this runs has genuinely never been classified by anyone — a real user tag would already have been applied or conflict-resolved by `_merge_pending_list_membership` earlier in the same `sync()` call. That's what makes a direct push safe and correct here without going through 05's merge machinery.

**Scope 2 design rationale:** no `sync.py` change is needed for this scope. `tag_star()` always reads the freshest local state (`store.load_stars()`) and freshest List classification (`client.fetch_lists()`), so a second `ghstars tag` call into a sibling Intent before an intervening sync will see the first call's already-staged `pending_list_ids` and correctly strip it too. By the time `_merge_pending_list_membership` sees a `pending_list_ids` set, it's already exclusivity-clean — that function's job is conflict arbitration (ADR 0001), not taxonomy-invariant enforcement, and the two should stay separate.

**Scope 3 design rationale:** `drain`'s bulk membership migration is the same blind-overwrite risk class ticket 05 fixes, just batched — one bad drain can clobber several concurrent edits at once instead of just one. Full Retriage-Queue routing (05's exact machinery) is heavier than drain needs, since drain has no user-staged "local pending edit" to preserve, just a computed migration intent — hence the lighter fetch-then-skip-diverged rule instead of reusing `_merge_pending_list_membership` directly.

**Open questions surfaced by the solutioning pass, not yet resolved — flag to the user if they affect implementation:**
- Scope 1: should the first-ever sync's N sequential default-pushes on an account with many unclassified stars be batched/throttled, or is a one-time cost acceptable as-is? Also worth sequencing against ticket 08 (`status`), which already assumes `Explore: General` counting works.
- Scope 2: should CLI output name the removed List (friendlier, needs an id→name lookup `tag_star()` doesn't currently have in scope) or just report id/count?
- Scope 3: partial-completion (skip stragglers, migrate the rest) vs. all-or-nothing atomic drain — a product decision for whoever implements ticket 07 later, not this ticket; scope 3 here only adds the acceptance criterion requiring *some* fresh-state check, not which failure mode.

## Comments (post-implementation, 2026-08-17)

Implemented as a worktree agent, all four scopes.

**Scope 1** (`core/sync.py`): `sync()` now calls `_apply_default_classification()`
right after `_merge_pending_list_membership()`. A target is a non-Archived
star with empty `list_ids` after the merge, **excluding** any star in
`failed_tag_pushes` or with a losing conflict this same sync. `Explore:
General` is looked up by name in the already-fetched `lists`, created
(public) at most once per call, and every target's push is isolated
(`except Exception`, same pattern as the merge step) into a new
`failed_default_pushes` field on `SyncResult`, reported by `sync_cmd`
the same way `failed_tag_pushes` already is.

**Scope 2** (`core/tagging.py`): `tag_star()` now strips any sibling List
of the same Category and a different lifecycle Intent
(Explore/Current/Retired) from `pending_list_ids` before appending the
target List's id — auto-resolved, never a hard error. Reference and
General (`intent=None`) Lists never strip and are never stripped.
`tag_star()`'s return became `TagResult` (`star` + `removed_list_ids`,
by id/count); `tag_cmd` reports removed ids in both plain-text (a
`(removed from N other List(s))` suffix) and `--json`
(`removed_list_ids` key). No `sync.py` change was needed for this scope,
as the pre-implementation Comments predicted.

**Scope 3 & 4**: doc-only edits exactly as scoped — ticket 07 gated on
05 with the fresh-state-check acceptance criterion added; ticket 13
gated on 14; ticket 10 got the malformed-List export criterion; ADR
0002 got a note on `config/`'s scaffolding being one-time, idempotent,
and never git-auto-committed by ghstars itself.

**Ticket-scoped `/code-review` findings, all real, all fixed:**

1. The initial `_apply_default_classification` target filter
   (`not archived and not list_ids`) could not tell "never classified"
   apart from "a real tag push just failed this sync" or "a merge
   conflict was just lost" — both leave `list_ids` empty too. A star in
   either state would get silently defaulted into `Explore: General`,
   contradicting `sync_cmd`'s "re-run `ghstars tag`" message in the
   first case and ticket 05's "never applied" conflict invariant in the
   second. Fixed by passing an `excluded` set (`failed_tag_pushes` +
   conflict `star_full_name`s) into the function; both are now skipped,
   left fully unclassified, not silently reassigned. Covered by
   `test_sync_reports_a_genuine_push_failure_and_keeps_going` (updated)
   and the new `test_sync_does_not_default_a_star_that_just_lost_a_merge_conflict`.
2. `client.create_list("Explore: General", ...)` had no try/except,
   unlike every other GitHub push in this file — a transient failure
   there would propagate out of `sync()` from inside `store.lock()`,
   aborting the whole sync and losing already-computed conflicts/pushes
   before they were ever persisted. Fixed: wrapped, and on failure every
   target is reported in `failed_default_pushes` while `stars`/`lists`
   are returned unchanged, so the rest of the sync's progress still
   gets saved. Covered by the new
   `test_sync_isolates_explore_general_creation_failure`.
3. The original per-star loop called `_apply_pushed_membership` once per
   target, an O(len(lists)) rebuild each time, for O(targets × lists)
   total work — all targets land in the same one List, so this is
   avoidable. Fixed: the loop now only pushes and isolates failures;
   `lists` is updated once, after the loop, for the single
   `Explore: General` entry.
4. The new ADR 0002 paragraph and the new `tagging.py`/`sync.py`
   docstrings violated this user's mandatory ASD-STE100 (`simple-english`)
   writing rule (long, multi-clause sentences). Rewritten into short,
   direct sentences throughout.

**Findings noted but deliberately not changed, all genuine
design/scope calls, not oversights:**

- A star whose List membership was cleared by the user directly on
  github.com (no local pending edit staged) is indistinguishable from
  "genuinely never classified" from local state alone, and will also
  get defaulted into `Explore: General`. The ticket's own Scope 1 text
  states the assignment rule unconditionally ("any star ... whose
  `list_ids` is still empty ... is assigned"), with no carve-out for
  this case, and there is no local signal today that could tell the
  two apart. Flagging this as a real edge case for a future ticket to
  resolve (e.g. a tombstone or an explicit "cleared" marker), not
  fixing it here since it would mean inventing new state tracking
  beyond this ticket's scope.
- `SyncResult` now carries two parallel `failed_*: list[str]` fields
  (`failed_tag_pushes`, `failed_default_pushes`) with two separately
  worded CLI warnings, rather than one structured push-failure report.
  This is exactly what the ticket's own Scope 1 text asked for ("e.g. a
  `failed_default_pushes`-shaped field on `SyncResult`... same style as
  the existing `failed_tag_pushes` warning") — kept as specified rather
  than redesigned into a shared shape unilaterally.
- The Explore/Current/Retired exclusivity invariant is enforced only at
  `tag_star()`'s single write path today; `_apply_default_classification`
  doesn't need it (a target's `list_ids` is always empty, so there's no
  sibling to strip), but a *future* write path that sets final List
  membership outside `tag_star()` — e.g. a Retriage Queue resolution
  command, or ticket 07's `category drain`/`rename` — would need to
  either reuse this check or re-derive it. Worth a note for whoever
  picks up ticket 07 or a Retriage-resolution command; out of scope to
  generalize into a shared primitive from a single call site today.

**Open questions from the pre-implementation Comments, resolved:**

- Scope 1 batching/throttling: left as a one-time sequential cost,
  same decision already made for pending tag pushes (see
  `docs/explanation/known-limitations.md`, new "Default-classification
  pushes are not batched either" section added alongside the existing
  "Pending tag pushes are not batched" one). Only matters once, on a
  first sync against an account with many pre-existing unclassified
  stars; every later sync only has newly-starred repos to push.
- Scope 2 id vs. name in CLI output: went with id/count, per the
  ticket's own stated safe default — `tag_star()` has no id→name
  lookup in scope, and adding one to resolve names is a small enough
  follow-up to leave for whoever actually wants friendlier output.

**Test status:** 109/109 passing, `mise run check` clean (fmt, lint,
mypy, tests) — 6 new `test_sync.py` cases plus 4 existing ones updated
for the new default-classification behavior (Scope 1); 4 new
`test_tagging.py` cases plus 5 existing ones updated for the new
`TagResult` return shape (Scope 2); 3 new `test_cli.py` cases for
`tag_cmd`'s removed-ids reporting.
