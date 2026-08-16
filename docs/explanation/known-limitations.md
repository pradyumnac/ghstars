# Known limitations

## Sync is not an atomic snapshot

`sync()` fetches stars and Lists as two separate GraphQL calls:
`fetch_stars()` first, `fetch_lists()` second. GitHub's real state can
change between the two calls.

**Effect:** if a repo is starred and added to a List during that gap,
`lists.json` lists it in that List's `items`, but `stars.json` has no
matching Star record. Code that joins `List.items` back onto
`Star.list_ids` has nothing to attach to for that repo.

**Trigger:** the repo must be starred and added to a List strictly
between the two calls. On a large account, `fetch_stars()` alone can
take tens of seconds, so the window is real, not theoretical.

**Recovery:** self-heals on the next sync. By then the repo was
starred well before that sync's `fetch_stars()` call.

**Not fully fixed:** `reconcile_list_membership()` now joins `List.items`
back onto `Star.list_ids`, skipping any list item with no matching
local Star, so the race no longer produces missing data — it just
resolves one sync late. It also leaves an already-Archived star
untouched, so a stale or racy `List.items` entry can never re-list a
star that was just unstarred (verified: an early version of this fix
did not have that guard, and code review caught a reproducible case
where it did). Reordering the two fetches would only move the race,
not remove it (an unstar between the calls creates the same problem
in the other direction), so reordering was not attempted.

## Sync always re-fetches everything

`sync()` has no incremental path. Every `ghstars sync` re-fetches all
starred repos, all owned forks, all follows, and every List's full
item membership from GitHub, regardless of what changed since the
last sync.

**Effect:** sync time scales with account size, not with what
changed. On a 1,529-star account, a sync takes about 45-50 seconds,
even when nothing changed since the last run.

**Why stars can't go incremental easily:** `starredRepositories` is
ordered newest-first, so *new* stars could in principle stop paging
early once a known `starred_at` is reached. But unstar detection
(`_carry_forward_archived`) needs the full current set to diff
against the previous one — GitHub has no "unstar" event feed, so
there is no cheaper way to learn what disappeared.

**The clear win, not yet taken:** the forks and follows fetches
(`_fetch_forked_parents`, `_fetch_followed_logins`) do not need a
full diff at all. They exist only to compute two `Star` fields and
could be fetched less often (e.g. cached, refreshed on a longer
interval) without touching star/unstar correctness.

## Pending tag pushes are not batched

Each `ghstars tag` stages a pending edit locally; `sync()` pushes them
one at a time. `update_list_membership_for_item` first resolves the
repo's GitHub node ID (`_resolve_repository_node_id`, one round trip),
then sends the mutation (a second round trip) — so N pending tags cost
2N sequential `gh api graphql` calls in that one sync, on top of the
sync's own fetches. GraphQL supports batching independent operations
into one request via aliases; this doesn't use that. Fine at the scale
one person tags between syncs; would need revisiting if that scale
changed.
