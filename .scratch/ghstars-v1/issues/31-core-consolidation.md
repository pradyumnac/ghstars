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

**Status:** ready-for-agent

## Scope A — One query in core

Move the whole discovery path into `ghstars.core`. The TUI calls the moved code.
Do not leave a second copy behind.

- [ ] Move every Filter into core: Category, Intent, List, Language, License,
      Owner, Fork, Followed, Unclassified, and starred-date recency.
- [ ] Move every Sort into core: name, star date, stargazer count, language,
      List count, and List name. Each Sort supports both directions.
- [ ] Move search into core. Search matches case-insensitive text in the Star
      name and the Star description.
- [ ] Define one Filter grammar in core. The TUI and the CLI parse the same
      grammar. Do not let the CLI invent a second vocabulary.
- [ ] The core query accepts more than one Filter. Core combines them with AND.
- [ ] Search and Filters compose in one deterministic order. Record that order.
- [ ] Move the recency cutoffs into core constants. Do not make them
      configurable. ADR 0008 rejected that.
- [ ] The core query accepts a deterministic limit and offset. A repeated call
      with the same arguments returns the same rows in the same order.
- [ ] Core resolves each Star's List names onto the returned row. A caller never
      joins `list_ids` against Lists itself.
- [ ] Core returns the available facet values: Categories, Intents, Lists,
      Languages, Licenses, and Owners.

### Filter arity changes TUI state

The TUI holds one Filter today. Core now holds a set. Decide how
`state/tui-state.toml` `filter` and `config/tui.toml` `default_filter` record a
set, and whether ADR 0008 needs an amendment. The TUI can keep a set of size one
until a later ticket gives it multi-Filter UI.

## Scope B — Surface behavior unification

Two surfaces disagree today. Fix both disagreements here, before ticket 30
freezes either one.

- [ ] Core excludes Archived Stars by default. The TUI drops them silently
      today; the CLI keeps them. Make the exclusion an explicit, named core
      default that both surfaces share.
- [ ] Core exposes an opt-in that includes Archived Stars.
- [ ] Fold `ghstars.core.export`'s Star selection onto the core query. Decide
      whether membership resolves through `List.items` or through
      `Star.list_ids`, and apply one answer everywhere.
- [ ] Record what changed for `export` output. Its selection path changes even
      when its results do not.
- [ ] Decide whether the TUI adopts bulk unstar or keeps refusing it. The TUI
      refuses bulk unstar today on blast-radius grounds. Ticket 30 gives the CLI
      bulk unstar. Record the reason for whichever answer you choose.

## Scope C — One mutation orchestrator

The TUI holds the only bulk-tag orchestrator. Move it down so the CLI reuses it.

- [ ] Add a core bulk-tag function. It resolves every repository node ID in one
      batch, threads the fetched Lists between calls, and isolates a failure for
      one repository from the others.
- [ ] The core bulk-tag function returns one result per repository. A failure
      for one repository never hides the result for another.
- [ ] The TUI calls the core bulk-tag function. Delete the TUI's own loop.
- [ ] Add a core bulk-unstar function with one result per repository.
- [ ] Single-Star `tag_star` and `unstar_star` keep working. The bulk functions
      build on them.

## Scope D — Shared rendering primitives

- [ ] Replace the duplicated field-selection and reorder code in the CLI
      renderer and the export writer with one core helper.
- [ ] Replace the separate default field lists for Stars, Lists, Retriage
      entries, and export with one core registry.
- [ ] The registry defines a basic set and a detailed set for each record type.
      Ticket 30 consumes both.

## Scope E — Proof

- [ ] The TUI tests and the new core tests exercise the same core query. No test
      reimplements a Filter, a Sort, or a search.
- [ ] A test proves the TUI and a direct core call return the same Stars for the
      same query.
- [ ] No TUI behavior regresses, except the two deliberate changes in Scope B.

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
