# 04 — Local tagging & two-way sync push

**What to build:** `ghstars tag` changes a Star's List membership locally; sync pushes the change to GitHub via `updateUserListsForItem`. That mutation replaces a Star's *entire* list membership per call — the sync engine must always compute and send the complete desired `listIds` set, never a delta. Writes are idempotent where feasible, so retrying after a timeout doesn't manufacture a spurious conflict against your own prior attempt (story 32). New Lists created as a side effect of tagging default to public, matching the account's existing Lists, with an explicit `isPrivate` override available (story 48).

**Blocked by:** 03.

**Status:** done

- [x] `ghstars tag <repo> <list>` changes membership locally
- [x] Sync pushes the change via `updateUserListsForItem`, always sending the full desired `listIds` set, never a delta
- [x] Retrying a timed-out write doesn't create a spurious conflict against the same prior attempt
- [x] A List created by tagging defaults to public unless `--private`/an explicit `isPrivate` override is given
- [x] Phone/web view of Lists reflects local tagging changes after sync (story 7)

## Comments

Implemented in commit `968614b`.

**Design**: `ghstars tag` creates a missing List for real immediately (safe,
additive), then stages the Star<->List membership as `Star.pending_list_ids`
(always the full desired set, never a delta) — no push yet. `sync()` gained a
push step that runs *before* the existing pull: it sends any pending edit via
`updateUserListsForItem`, then the existing fetch/reconcile pipeline naturally
picks up the pushed state on the fresh pull. No separate merge logic needed
for this ticket's scope (that's ticket 05's three-way merge, deliberately not
built here).

**Idempotency (story 32)** falls out of the design for free: since
`pending_list_ids` is always the full desired set and `updateUserListsForItem`
replaces rather than merges, retrying a failed/partial push is a harmless
no-op on GitHub's side.

**Live verification**: initially blocked — `createUserList` (and, confirmed
now, `updateUserListsForItem` too) requires the `user` OAuth scope, which the
`gh` token didn't have. That failure propagated cleanly through the existing
hard-fail path (exit 1, no traceback, no partial local state, checked in both
`--json` and plain-text modes) — documented in `README.md`'s Authenticate
section, since every real `ghstars` user hits this the first time they tag
anything. Once the scope was granted, ran the full path for real: created a
List (`zzz-ghstars-verify-delete-me`), tagged a real starred repo into it
alongside its existing membership (confirmed the full-desired-set/no-delta
behavior — both list IDs ended up in `pending_list_ids`), ran `ghstars sync`,
and independently confirmed via a raw `gh api graphql node(id:)` query
(bypassing ghstars entirely) that the List really contains the repo — the
same thing phone/web would show. Local state settled correctly too:
`list_ids` populated with both IDs, `pending_list_ids` cleared to `None`.

**`/code-review` findings, all fixed** (see commit message for the full list):
`tag_star()` didn't reject an already-Archived star; `_push_pending_list_membership`
had no per-star error isolation and could get permanently stuck retrying a
doomed push, blocking every future sync — fixed with per-star isolation, a new
`SyncResult.failed_tag_pushes` field, and a CLI warning; the "list already
exists" check used the stale local cache instead of live GitHub state, risking
a duplicate List; missing schema parse tests for the two new mutations; a
stale docstring claim about round-trip cost; and a non-STE-compliant README
sentence. Also fixed, found while testing: `FakeGitHubClient.fetch_stars()`
was leaking `pending_list_ids` back out, which no real client structurally
can.
