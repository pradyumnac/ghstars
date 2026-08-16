# 16 — Push a tag edit immediately, like unstar already does

**What to build:** make `ghstars tag` push its edit immediately, the same way `ghstars unstar` already does, instead of staging it as `pending_list_ids` for the next `ghstars sync` to push. This is **not** a generic "all write ops" ticket — analysis below shows `unstar` doesn't have the problem this ticket is about.

**Why `unstar` doesn't need this:** `unstar_cmd` already calls `client.remove_star()` for real, synchronously, and updates local state (`archive_star`, `remove_star_from_lists`) in the same command — no follow-up `ghstars sync` is needed for either GitHub or local state to reflect it. It's Star-existence (the Archived axis, ticket 06), not List-membership, so it was never going to go through ticket 05's three-way merge regardless of timing — there's no "wait for conflict arbitration" reason to defer it, and it doesn't. `tag` is the only current write command that requires a second command (`sync`) to actually take effect on GitHub.

**Blocked by:** 04, 05. Hard-blocked on 05 specifically: today, deferring the push doesn't actually buy any conflict-safety (see ticket 05's Comments — the current push is unconditional, not compared against anything). Making `tag` push immediately is only a *safe* trade once 05 exists and can run the same base-vs-current-vs-pending comparison synchronously inside `ghstars tag` itself, before pushing — otherwise this ticket would just be reintroducing the blind-overwrite problem 05 exists to fix, in a smaller window instead of a larger one.

**Status:** ready-for-agent — needs design, not yet speced

**Open questions to resolve before implementation:**

- [ ] Once 05 exists, can `tag_star()` call the same three-way-merge logic synchronously (fetch current GitHub state for just the affected star/lists, compare against base + the new edit, push or Retriage) without paying for a full account-wide sync? This is the real efficiency question — narrowing the *comparison* to one star, not skipping it.
- [ ] What happens to `pending_list_ids` and `_push_pending_list_membership` in `sync()` if `tag` stops staging edits? Does staged-and-deferred become a fallback path only (e.g. for a failed immediate push), or does it disappear entirely?
- [ ] Does an immediate per-tag push change the API cost story? Trades ~27 points (full sync) for a handful of points per `tag` call — better if the user tags occasionally, worse if they tag many repos in a row without an intervening sync (N narrow round-trips vs. one batched sync). Worth measuring against real usage patterns, not just assuming immediate is strictly better.

**Acceptance criteria:** none yet — write these once 05 lands and the questions above are resolved into an actual design.
