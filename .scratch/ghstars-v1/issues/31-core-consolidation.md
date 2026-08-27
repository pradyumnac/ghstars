# 31 — Core consolidation: one query, one orchestrator

**What to build:** Move every shared behavior out of the TUI and into
`ghstars.core`. After this ticket, no surface holds its own selection, sorting,
search, or mutation-orchestration logic. The TUI keeps its presentation only.

Today the TUI holds the single implementation of Star discovery. The CLI has
none. `ghstars.core.export` holds a third, independent selection path. Three
code paths answer one question, and they can disagree. Ticket 30 cannot define a
stable agent contract on top of that, so this ticket lands first.

This ticket adds no new CLI surface. It moves code, unifies two behaviors that
already disagree, and proves that both surfaces return the same result.

**Blocked by:** None — can start immediately.

**Status:** done — all five scopes landed on `main`.

## Scope A — One query in core

Move the whole discovery path into `ghstars.core`. The TUI calls the moved code.
Do not leave a second copy behind.

- [x] Move every Filter into core: Category, Intent, List, Language, License,
      Owner, Fork, Followed, Unclassified, and starred-date recency.
- [x] Move every Sort into core: name, star date, stargazer count, language,
      List count, and List name. Each Sort supports both directions.
- [x] Move search into core. Search matches case-insensitive text in the Star
      name and the Star description.
- [x] Define one Filter grammar in core. The TUI and the CLI parse the same
      grammar. Do not let the CLI invent a second vocabulary.
- [x] The core query accepts more than one Filter. Core combines them with AND.
- [x] Search and Filters compose in one deterministic order. Record that order.
- [x] Move the recency cutoffs into core constants. Do not make them
      configurable. ADR 0008 rejected that.
- [x] The core query accepts a deterministic limit and offset. A repeated call
      with the same arguments returns the same rows in the same order.
- [x] Core resolves each Star's List names onto the returned row. A caller never
      joins `list_ids` against Lists itself.
- [x] Core returns the available facet values: Categories, Intents, Lists,
      Languages, Licenses, and Owners.

**Delivered:** `src/ghstars/core/discovery.py` — `query_stars()`, `available_facets()`,
`StarRow` (a `Star` plus resolved `list_names`, not an extended `Star`),
`Facets`, `SortMode`, `RECENCY_CUTOFFS`, `OLDER_THAN_CUTOFF`. Compose order:
Archived-exclusion, then Filters (AND), then search, then sort, then
offset/limit. Landed on `main` at `8acfc83`.

### Filter arity changes TUI state

The TUI holds one Filter today. Core now holds a set. Decide how
`state/tui-state.toml` `filter` and `config/tui.toml` `default_filter` record a
set, and whether ADR 0008 needs an amendment. The TUI can keep a set of size one
until a later ticket gives it multi-Filter UI.

## Scope B — Surface behavior unification

Two surfaces disagree today. Fix both disagreements here, before ticket 30
freezes either one.

- [x] Core excludes Archived Stars by default. The TUI drops them silently
      today; the CLI keeps them. Make the exclusion an explicit, named core
      default that both surfaces share.
- [x] Core exposes an opt-in that includes Archived Stars.

      **Delivered:** `query_stars(..., include_archived=False)` — the default.
      `DEFAULT_INCLUDE_ARCHIVED` in `core/discovery.py`. `_reload_local_state`
      in the TUI no longer filters Archived Stars itself; the query does.

- [x] Fold `ghstars.core.export`'s Star selection onto the core query. Decide
      whether membership resolves through `List.items` or through
      `Star.list_ids`, and apply one answer everywhere.
- [x] Record what changed for `export` output. Its selection path changes even
      when its results do not.

      **Decision:** `Star.list_ids` is the one source of truth, matching what
      `query_stars` (Scope A) already uses. `select_stars()` in
      `core/export.py` no longer scans `List.items` directly; it calls
      `query_stars(stars, lists, filters=[f"list:{lst.id}"],
      include_archived=True)` once per List its `ExportEntry` matched, and
      unions the results (deduped by `full_name`). One call per List, not one
      call with several `list:` Filters, because `query_stars`'s Filter
      grammar AND-combines Filters and cannot express "belongs to any of
      these Lists" (an OR across Lists) in a single call.
      `include_archived=True` preserves `export`'s historical behaviour of
      including Archived Stars, which the TUI/CLI query default excludes --
      only the membership source changed, not what counts as in-scope.

      **What changed for output:** in practice, nothing, for any state
      `sync()` has produced. `reconcile_list_membership` (`core/sync.py`)
      keeps `List.items` and every Star's `list_ids` in agreement after every
      sync, so the old `List.items` scan and the new `list_ids` resolution
      agree on every reachable state. The change only bites on an
      unreconciled state that should not exist post-sync (e.g. hand-edited
      `state/lists.json`) -- there, `export` now trusts the Star's own
      `list_ids`, the same source every other surface trusts, instead of a
      List's possibly-stale `items` mirror. Proven by
      `test_select_stars_resolves_membership_through_star_list_ids` in
      `tests/test_export.py`, which deliberately diverges the two fixtures
      and asserts `list_ids` wins.
- [x] Decide whether the TUI adopts bulk unstar or keeps refusing it. The TUI
      refuses bulk unstar today on blast-radius grounds. Ticket 30 gives the CLI
      bulk unstar. Record the reason for whichever answer you choose.

      **Decision:** the TUI keeps refusing bulk unstar. Its existing reasoning
      stands — unstarring several repos from one confirm dialog is a much
      larger blast radius than bulk-tagging into the same List. Ticket 30 gives
      the CLI bulk unstar deliberately, gated by its confirmation rule. The two
      surfaces disagree on purpose; this is not a parity gap to close.

## Scope C — One mutation orchestrator

The TUI holds the only bulk-tag orchestrator. Move it down so the CLI reuses it.

- [x] Add a core bulk-tag function. It resolves every repository node ID in one
      batch, threads the fetched Lists between calls, and isolates a failure for
      one repository from the others.
- [x] The core bulk-tag function returns one result per repository. A failure
      for one repository never hides the result for another.
- [x] The TUI calls the core bulk-tag function. Delete the TUI's own loop.
- [x] Add a core bulk-unstar function with one result per repository.
- [x] Single-Star `tag_star` and `unstar_star` keep working. The bulk functions
      build on them.

**Delivered:** `bulk_tag_stars()` in `core/tagging.py` (`BulkTagOutcome`
per target), `bulk_unstar_stars()` in `core/unstar.py` (`BulkUnstarOutcome`
per target). Landed on `main` at `8acfc83`.

## Scope D — Shared rendering primitives

- [x] Replace the duplicated field-selection and reorder code in the CLI
      renderer and the export writer with one core helper.
- [x] Replace the separate default field lists for Stars, Lists, Retriage
      entries, and export with one core registry.
- [x] The registry defines a basic set and a detailed set for each record type.
      Ticket 30 consumes both.

**Delivered:** `src/ghstars/core/fields.py` — `FIELD_REGISTRY`, `FieldSet`
(a `basic`/`detailed` tuple pair), `select_fields()`. Four registry keys:
`star`, `list`, `retriage`, `export` — `star`/`export` both wrap `Star` but
keep separate `basic` sets since their defaults always disagreed. Registry
entries are defined against plain `Star`, not `StarRow` (`Star` carries no
List-name field); ticket 30 adds a `StarRow`-based entry when it wires
`ghstars list` through `query_stars()`. Landed on `feat/31-integration` at
`adb8a63`; a review-found bug (`--fields ""` dumping to `{}` instead of
falling back to every field) was fixed in the same merge.

## Scope E — Proof

- [x] The TUI tests and the new core tests exercise the same core query. No test
      reimplements a Filter, a Sort, or a search.
- [x] A test proves the TUI and a direct core call return the same Stars for the
      same query.
- [x] No TUI behavior regresses, except the two deliberate changes in Scope B.

**Delivered:** `test_visible_rows_matches_a_direct_query_stars_call` in
`tests/test_tui.py` — asserts `TuiApp._visible_rows()` and a direct
`query_stars()` call return the same Stars for the same Filter/sort/search.
Every existing `test_tui.py` Filter/Sort/search test already exercises
`_visible_rows()`, which forwards to `query_stars()` — none reimplements the
logic itself.

## Non-goals

- Do not add any new CLI command or option. Ticket 30 owns the CLI surface.
- Do not move TUI layouts, colours, keybindings, view state, or config-editor
  behavior into core.
- Do not add a config file or a config field. Ticket 32 owns config.
- Do not change the JSON output shape or the exit codes. Ticket 30 owns them.

## Completion gate for ticket 30

Before ticket 30 starts, document the core query signature, the Filter grammar,
the facet function, the bulk-tag and bulk-unstar signatures, the field registry,
and the Archived default. Ticket 30 has criteria that reference this ticket by
number. Re-check each one against the delivered signatures and update it where
the signature differs.
