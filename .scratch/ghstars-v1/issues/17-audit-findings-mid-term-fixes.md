# 17 — Mid-term bug fixes from the spec/issues consistency audit

**What to build:** four fixes bundled together, all originating from the 2026-08-17 spec/issues consistency audit and its follow-up solutioning pass (see `HANDOFF.md`'s now-superseded "Spec/issues consistency audit" and "Solutioning proposals" sections for full traceability — this ticket is the landing place for both, replacing them as the source of truth going forward):

1. Implement the `Explore: General` default classification (spec story 4) — currently unimplemented anywhere in the codebase.
2. Enforce Intent mutual exclusivity (spec story 16) — currently unenforced in `tag_star()`.
3. Gate ticket 07 (category rename & drain) on ticket 05, with a fresh-state-check safety rule.
4. Three minor doc/ticket fixes: ticket 13's dependency on 14, a `config/` governance note, and a ticket 10 acceptance criterion for malformed List names.

**Blocked by:** 05 (done, merged `e48b704`).

**Status:** ready-for-agent

## Scope 1 — `Explore: General` default classification

- [ ] Inside `sync()` (`core/sync.py`), after `_merge_pending_list_membership()` returns and before the retriage/save block: any non-archived star whose `list_ids` is still empty at that point is assigned to `Explore: General`.
- [ ] `Explore: General` List is looked up in the already-fetched `lists`; created on GitHub (public, per story 48) only if it doesn't exist yet — lazy, not eager, and idempotent across syncs.
- [ ] The membership push for a newly-defaulted star is a direct full-replace call (nothing else to preserve on an empty `list_ids`) — **not** routed through ticket 05's three-way merge. A synthetic default has no staged local edit or remote opinion to reconcile against, so conflict arbitration doesn't apply here.
- [ ] Per-star push failures are isolated (same pattern as `_merge_pending_list_membership`'s `except Exception`) and reported back (e.g. a `failed_default_pushes`-shaped field on `SyncResult`), never fatal to the whole sync.

## Scope 2 — Intent mutual exclusivity

- [ ] `tag_star()` (`core/tagging.py`): when the target List's intent is Explore, Current, or Retired, strip any id already in `pending_list_ids` that belongs to a sibling List of the *same Category* and a *different* one of those three lifecycle Intents, before appending the new List's id.
- [ ] Auto-resolve, not a hard error — spec story 17 (move a Star from `Current` to `Retired` via a single `tag` call, without unstarring) requires this to just work, not require a manual untag first.
- [ ] `tag_star()`'s return communicates what (if anything) was removed — extend its return shape (e.g. a small `TagResult` alongside the existing `Star`, matching `SyncResult`'s pattern) — and `tag_cmd` (`cli/__init__.py`) reports it in both plain-text and `--json` output, not silently.
- [ ] `Reference`-intent Lists and unprefixed General Lists (`intent=None`) are exempt from exclusivity — never treated as a conflict candidate, never stripped.

## Scope 3 — Gate ticket 07 on ticket 05

- [ ] Edit `.scratch/ghstars-v1/issues/07-category-rename-drain.md`: change `Blocked by: 04` to `Blocked by: 04, 05`.
- [ ] Add a new acceptance criterion to ticket 07: `drain`/`rename` fetch fresh GitHub state before computing/writing the bulk change, and **skip and report** (never silently overwrite) any Star whose live List membership has already diverged from what triggered the migration.
- [ ] This ticket (17) only edits ticket 07's file — it does not implement `category rename`/`category drain` themselves; that's still ticket 07's job, now correctly scoped.

## Scope 4 — Minor doc/ticket fixes

- [ ] `.scratch/ghstars-v1/issues/13-*.md`: add `14` to its `Blocked by:` list.
- [ ] `docs/adr/0002-*.md` or `docs/explanation/known-limitations.md`: add a short note documenting that `~/.ghstars/config/` scaffolding (introduced by commit `0fe4180`) is one-time, idempotent, and never git-auto-committed — giving that ad-hoc commit a documented owner.
- [ ] `.scratch/ghstars-v1/issues/10-*.md`: add an acceptance criterion — export skips and reports a malformed List rather than exporting it under a guessed Intent/Category.

## Comments (pre-implementation, from the audit's solutioning pass, 2026-08-17)

**Scope 1 design rationale:** an empty-`list_ids` star at the point this runs has genuinely never been classified by anyone — a real user tag would already have been applied or conflict-resolved by `_merge_pending_list_membership` earlier in the same `sync()` call. That's what makes a direct push safe and correct here without going through 05's merge machinery.

**Scope 2 design rationale:** no `sync.py` change is needed for this scope. `tag_star()` always reads the freshest local state (`store.load_stars()`) and freshest List classification (`client.fetch_lists()`), so a second `ghstars tag` call into a sibling Intent before an intervening sync will see the first call's already-staged `pending_list_ids` and correctly strip it too. By the time `_merge_pending_list_membership` sees a `pending_list_ids` set, it's already exclusivity-clean — that function's job is conflict arbitration (ADR 0001), not taxonomy-invariant enforcement, and the two should stay separate.

**Scope 3 design rationale:** `drain`'s bulk membership migration is the same blind-overwrite risk class ticket 05 fixes, just batched — one bad drain can clobber several concurrent edits at once instead of just one. Full Retriage-Queue routing (05's exact machinery) is heavier than drain needs, since drain has no user-staged "local pending edit" to preserve, just a computed migration intent — hence the lighter fetch-then-skip-diverged rule instead of reusing `_merge_pending_list_membership` directly.

**Open questions surfaced by the solutioning pass, not yet resolved — flag to the user if they affect implementation:**
- Scope 1: should the first-ever sync's N sequential default-pushes on an account with many unclassified stars be batched/throttled, or is a one-time cost acceptable as-is? Also worth sequencing against ticket 08 (`status`), which already assumes `Explore: General` counting works.
- Scope 2: should CLI output name the removed List (friendlier, needs an id→name lookup `tag_star()` doesn't currently have in scope) or just report id/count?
- Scope 3: partial-completion (skip stragglers, migrate the rest) vs. all-or-nothing atomic drain — a product decision for whoever implements ticket 07 later, not this ticket; scope 3 here only adds the acceptance criterion requiring *some* fresh-state check, not which failure mode.
