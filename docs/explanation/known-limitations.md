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

**Measured API cost** (same account, steady state, `rateLimit.cost`
confirmed at 1 point per `gh api graphql` call for these query shapes):
one plain sync costs **~27 points** — roughly 16 for paginating
`starredRepositories`, 1 for owned forks, 2 for following, 1 for the
Lists list, 1 per List for its items (7 here). Against the 5000
points/hour budget, that's not a practical day-to-day problem — but it
is a fixed cost paid on every sync no matter how small the actual
change. Since ticket 16, a single `ghstars tag` no longer needs to wait
for (or trigger) a sync at all — it pushes immediately, at its own
much smaller cost (see "`ghstars tag` pushes are not batched" below).

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

## `ghstars tag` pushes are not batched (per single-tag call)

Since ticket 16, `ghstars tag` pushes its edit to GitHub immediately,
in the same call — it no longer stages a pending edit for `sync()` to
push later (see ADR 0004 for why the older staged-edit machinery stays
in the codebase, unused, rather than being deleted). Each push still
costs two round trips: `update_list_membership_for_item` first resolves
the repo's GitHub node ID (`_resolve_repository_node_id`), then sends
the mutation. A single `ghstars tag` call was always going to pay this
regardless of when the push happens; GraphQL's request-aliasing
batching only helps when there is more than one repo to resolve/push
in the same operation, which a single CLI invocation never has.

The TUI's bulk-tag path *does* batch what it can: it resolves every
selected star's node ID in one aliased `resolve_repository_node_ids()`
request up front (`RealGitHubClient`, `github/client.py`), instead of
paying the resolution round trip per star. The membership-update
mutations themselves stay sequential, one per star — batching those too
via aliasing was considered and rejected (breaks per-star failure
isolation and the TUI's incremental progress notification; GitHub's
rate-limit points are charged by query complexity, not request count,
so it would not even save quota) unless a real bulk-tag workload proves
the ID-lookup batch alone isn't enough.

## `category drain` pushes are not batched either

`drain_category()` (ticket 07) migrates each Star one at a time, the
same 2-round-trip-per-Star cost as a pending tag push. A drain across
N Stars costs 2N sequential `gh api graphql` calls, plus one call per
newly-created destination List. A drain is a deliberate, occasional
user action, not part of every sync, so this is accepted as-is —
revisit only if a real drain across a very large Category proves slow.
