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

**Not fixed:** reordering the two fetches only moves the race; it does
not remove it (an unstar between the calls creates the same problem in
the other direction). A real fix needs defensive handling — reconcile
`List.items` against `Star.list_ids`, and skip or log any list item
with no matching local Star — not just a fetch-order change.
