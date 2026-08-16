# 06 — Unstar detection & Archived state

**What to build:** Handling for the **Star-existence axis** — distinct from the List-membership merge in 05. Sync detects when a repo has been unstarred on GitHub since the last sync and marks the local record `Archived` (a Star property, never an Intent — see CONTEXT.md) rather than deleting it or letting it silently vanish. History for an unstarred repo is never deleted, so the user can still see when and why they once starred it. `ghstars unstar` performs a real unstar against GitHub via a `removeStar` mutation, making the CLI/TUI a real control surface rather than a local shadow copy.

**Blocked by:** 02.

**Status:** done

- [x] Sync detects a GitHub-side unstar (repo present in last snapshot, absent from current fetch) and sets `archived`/`archived_at` on the local `Star` record
- [x] Archived records are never deleted locally; full history remains visible
- [x] `ghstars unstar <repo>` calls GitHub's `removeStar` mutation and unstars for real
- [x] Archived is never conflated with Retired (Retired is an Intent value on a List, orthogonal to whether the Star itself is still starred)

## Comments

Implemented in commits `046f2b6`/`fc383a8`.

`core/sync.py`: added `_carry_forward_archived()` — a small helper, deliberately
kept separate from `sync()`'s main body per the ticket's note that ticket 03 is
touching `sync()` in parallel. `sync()` now loads the previous snapshot before
fetching, diffs by `full_name`, and carries forward any star missing from the
fresh fetch marked `archived=True`/`archived_at=now` (idempotent — a star
already archived from an earlier sync is carried forward unchanged, so
repeated syncs don't keep bumping `archived_at`; a star that reappears in a
later fetch is naturally un-archived, since it comes back through the fresh
`current` list). `archive_star()` also clears `list_ids` when archiving, since
an unstarred repo drops out of every GitHub List automatically — keeping a
stale membership list around would misrepresent reality.

**`item_id`/node-ID design call:** kept `item_id` as the Star's `full_name`
(`owner/repo`) everywhere in `GitHubClient` — the same key `FakeGitHubClient`,
`update_list_membership_for_item`, and the state store already use. GraphQL's
`removeStar` mutation needs GitHub's opaque node ID (`starrableId`), not
`owner/repo`, so `RealGitHubClient.remove_star` resolves it internally via a
`repository(owner, name) { id }` lookup before firing the mutation — one extra
round trip per unstar, acceptable since this is a single, explicitly
user-initiated action, not a batch/paginated path. Documented this decision in
`GitHubClient.remove_star`'s docstring so it's visible at the seam itself, not
just here.

Verified the mutation shape via read-only introspection against the live
GitHub schema (never executed): `removeStar(input: {starrableId: ID!}):
RemoveStarPayload { starrable { id } }`, confirmed `starrableId` is required
and non-null, confirmed `repository(owner, name) { id }` returns the needed
node ID (tested read-only against `octocat/Hello-World`). **The real
`removeStar` mutation was never invoked during implementation or testing** —
all `remove_star` behavior was exercised only against `FakeGitHubClient`
(already covered by ticket 01's `test_remove_star_drops_it_from_fetch_stars`
and `test_remove_star_clears_it_from_list_items`, unchanged here).

`ghstars unstar <repo>`: calls `client.remove_star`, then marks the local
record Archived if one exists (does not hard-fail if no local record is
found — the GitHub-side unstar already succeeded regardless, so failing here
would misrepresent that as an error; `--json` output includes an honest
`archived_locally` field instead so an agent can tell the two cases apart).

`/code-review` (medium-effort, forked) flagged six things, five fixed:
1. `sync()`'s new read-modify-write (`load_stars` then `save_stars`) wasn't
   held under one lock, so a concurrent `ghstars unstar` could race and lose
   an update — fixed by wrapping both in a single `with store.lock():` span
   in both `sync()` and `unstar_cmd` (confirmed `filelock.FileLock` is
   reentrant within a thread, so the nested locking inside `load_stars`/
   `save_stars` doesn't deadlock).
2. `sync()` reading `stars.json` up front removed its previous ability to
   self-heal a corrupted local file (it used to just blindly overwrite) —
   fixed with `_load_previous_stars()`, which treats a corrupt/unreadable
   previous snapshot as "no history to diff against" rather than a fatal
   error; added `test_sync_self_heals_when_previous_state_is_corrupt`.
3. `remove_star` validated `RemoveStarResponse` but never checked that
   `starrable` was non-null, so a mutation GitHub silently no-ops could be
   treated as success — fixed with an explicit null check raising
   `GitHubApiError`.
4. `unstar_cmd` always reported `archived: true` even when no local record
   matched the repo — fixed: `--json` now reports `archived_locally`
   honestly, and the human-readable message distinguishes the two cases.
5. `RepositoryNode`/`StarrableNode` were structurally identical — unified
   into one `NodeId` model.

Not fixed (documented, not silently expanded in scope): a repo rename or
owner transfer on GitHub looks identical to an unstar-then-new-star under
`full_name`-based diffing (the old name gets archived, the new name shows up
as a brand-new Star with a fresh `first_seen`). Fixing this properly needs a
stable GitHub node-ID field on `Star` itself, populated by
`RealGitHubClient.fetch_stars` (already-shipped ticket 02 code) and used for
matching instead of `full_name` — out of this ticket's blast radius given the
minimal-footprint instruction, and `full_name`-as-identity is an assumption
inherited from tickets 01/02 (`FakeGitHubClient`, the state store, and the
whole CLI already key everything off it), not introduced here.
