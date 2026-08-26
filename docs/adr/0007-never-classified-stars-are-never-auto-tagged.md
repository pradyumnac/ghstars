# 0007 — Never-classified Stars are never auto-tagged; "Unclassified" is a local, derived view

## Status

accepted

## Implemented

done

## Context

Spec story 4 originally read: "unclassified new stars land in `Explore:
General` by default, so that nothing slips through without at least a
landing spot." `sync()`'s `_apply_default_classification` (ticket 17)
implemented this literally: any Star left with empty `list_ids` after
the pending-tag merge got pushed, for real, into a `Explore: General`
List on GitHub — creating that List on first use if it didn't exist.

In practice, on a first sync against an existing account with many
never-classified stars, this pushes one real `gh api graphql` mutation
per star, sequentially (`docs/explanation/known-limitations.md`'s
"default-classification pushes are not batched" note) — a first sync
against ~1,500 stars, most unclassified, cost potentially 1,000+
sequential round trips and made the CLI look hung for many minutes.

Looking past the performance problem, the behavior itself was
questioned: why should ghstars write anything to the user's real GitHub
account for a star nobody has decided anything about yet? `Explore:
General`'s own name space is already a legitimate, intentful List a
user can create and use like any other (`CONTEXT.md`'s "General List"
concept, unprefixed List name, outside the Intent/Category taxonomy) —
conflating that with "the auto-generated bucket for whatever ghstars
couldn't place" overloads one name with two different meanings, and
means the user's own choice to genuinely use `Explore: General` for
something gets mixed in with stars ghstars parked there without being
asked.

## Decision

`sync()` never creates or writes to any List on behalf of a
never-classified Star. A Star with empty `list_ids` after the pending-
tag merge is left exactly as-is — no default push, no List creation.

"Unclassified" becomes a derived, local-only view: `list_ids == [] and
not archived`, computed fresh every time from whatever `sync()` already
fetched — never a separate fact that needs writing anywhere or
reconciling against a future sync. `ghstars status`'s
`unclassified_count` field (ticket 08) counts this directly.

This does not revisit ADR 0001 (GitHub is the sole source of truth for
List existence and membership): "unclassified" is not persisted state
that could disagree with GitHub — it is a pure function of `list_ids`,
which itself always comes straight from the last `fetch_lists()`/
`fetch_stars()` call. There is nothing to arbitrate.

`_apply_default_classification`, `SyncResult.failed_default_pushes`,
and the `EXPLORE_GENERAL` constant are removed outright, not kept
dormant — unlike ADR 0004's `pending_list_ids` machinery, nothing here
is reusable scaffolding for a plausible future feature; it is simply a
default this decision reverses.

## Consequences

- A first sync against a large, mostly-unclassified account is now
  bounded by the fetch pagination cost alone (`PAGE_SIZE`-sized pages),
  not by one mutation per unclassified star — no batching work was
  needed because there is no longer a push to batch.
- `Explore: General` is no longer special-cased anywhere in `ghstars
  sync`. A user who wants a literal "Explore: General" List still gets
  ordinary taxonomy behavior for it (`Explore` intent, `General`
  category) if they create and use it themselves via `ghstars tag`.
- `ghstars status`'s `unclassified_count` no longer requires an
  `Explore: General` List to exist locally at all — it is 0 whenever
  every Star has some List membership or is Archived, regardless of
  whether that List has ever been created.
- A future surface (CLI or TUI) that wants to show "Unclassified" as a
  browsable group should filter on `list_ids == [] and not archived`
  directly, not look for a List by name.

## Alternatives considered

- **Batch the default-classification push instead of removing it** —
  rejected. Batching (aliased node-ID resolution the way
  `resolve_repository_node_ids` already does for tag pushes) would have
  fixed the performance problem but not the underlying question: should
  ghstars ever write a real, publicly visible List membership the user
  never asked for. Once that was answered no, batching the push had
  nothing left to optimize.
- **Keep pushing to `Explore: General`, but make it opt-in via a sync
  flag** — rejected as needless complexity. A flag the user must
  remember to pass (or not) is a worse default than simply never doing
  it; anyone who wants stars actually classified into `Explore: General`
  can already do that directly with `ghstars tag`.
