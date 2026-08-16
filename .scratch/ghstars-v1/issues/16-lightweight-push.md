# 16 — Lightweight push for a single pending tag edit

**What to build:** a cheaper way to push one `ghstars tag` edit than running a full `ghstars sync`. Today the only push path is `sync()`, which always pays the full pull cost (~27 points on a 1,529-star account, see `docs/explanation/known-limitations.md`) on top of the 2-point push itself, even for a single tag change.

**Not a webhook/hook system** — GitHub doesn't emit webhook events for personal starring or List-membership changes, so there's no inbound mechanism to build here. This is purely about the outbound path: push the pending edit(s) without also doing the full `fetch_stars`/`fetch_lists`/reconcile pipeline.

**Blocked by:** 04, 05.

**Status:** ready-for-agent — needs design, not yet speced

**Open questions to resolve before implementation (not yet decided):**

- [ ] What does correctness look like without the full pull? `reconcile_list_membership()` currently gives a pushed edit its final `list_ids` by re-deriving it from a fresh `fetch_lists()`. A lightweight push would need to either (a) optimistically set `list_ids` to the pushed `pending_list_ids` without re-fetching, accepting it could drift from GitHub truth until the next full sync, or (b) fetch just the affected List(s)' membership (cheap — 1-2 points) rather than every List.
- [ ] Does this need ticket 05's three-way merge machinery first? Skipping the full pull means skipping the conflict-detection that a full sync would otherwise do — pushing blind is riskier than pushing after seeing current GitHub state. This ticket may not be safe to build before 05 lands.
- [ ] New CLI surface: a `--push` flag on `ghstars tag` itself (tag + immediately push, skip staging)? A separate `ghstars push` command? Automatic push after N pending edits accumulate?
- [ ] Does `_carry_forward_archived`'s need for a full current-stars fetch (to detect unstars) mean this can only ever skip the *Lists* portion of a sync, never the *stars* portion?

**Acceptance criteria:** none yet — write these once the open questions above are resolved into an actual design.
