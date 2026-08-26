# 30 — CLI feature parity for agent use

**What to build:** Bring the CLI data and action flow into parity with the
implemented TUI workflows that an agent needs. Keep presentation and TUI config
out of the CLI. Complete this ticket before ticket 14 defines the agent skill.

The last CLI-focused work added `status --json`, immediate `tag`, sync progress,
and shared unstar orchestration. Later TUI work added discovery filters, search,
sort, bulk tagging, collection counts, API status, and explicit sync state. The
CLI does not expose all of those capabilities as stable agent contracts.

**Blocked by:** None.

**Status:** ready-for-agent

## Scope 0 — Agent-consumption readiness review

Evaluate the CLI as an interface for an agentic LLM before implementation.
Repeat the evaluation after all other scopes pass.

- [ ] Inventory each command and classify it as ready, needs work, or unsuitable
      for agent use.
- [ ] Test the complete agent flow: inspect state, discover Stars, sync when
      required, classify one or many Stars, review Retriage Queue entries,
      unstar explicit Stars, export data, and inspect history.
- [ ] Check JSON schema stability, exit codes, standard output purity, standard
      error use, partial failures, and error messages.
- [ ] Check that large outputs are bounded and can be paged without losing a
      stable order.
- [ ] Check that every network call is explicit and every mutation names its
      targets.
- [ ] Check that destructive actions require a clear confirmation contract that
      also works without a terminal.
- [ ] Measure the command count and output size for the tested agent flows.
- [ ] Record a go or no-go verdict in this ticket. List every blocker and link
      each blocker to an acceptance criterion.
- [ ] Do not start ticket 14 until the final verdict is go.

## Scope 1 — Shared discovery query

Move discovery rules out of `ghstars.tui.app` into `ghstars.core`. Use the same
query code from the TUI and CLI. Do not create two filter implementations.

- [ ] `ghstars list` filters by Category, Intent, List, Language, License,
      Owner, Fork, Followed, Unclassified, and starred-date recency.
- [ ] `ghstars list` searches case-insensitive text in Star name and
      description.
- [ ] `ghstars list` sorts by name, star date, stargazer count, language, List
      count, and List name. Each sort supports both directions.
- [ ] Search and one Filter compose in the same order as the TUI.
- [ ] The command supports deterministic pagination or a deterministic result
      limit for large accounts.
- [ ] `--json` and `--fields` work with every discovery option.
- [ ] JSON output contains only machine data. Human status text stays on
      standard error or does not print.
- [ ] TUI tests and CLI tests use the same core query rules.

## Scope 2 — Explicit bulk actions

Use explicit repository names for every bulk mutation. A Filter can discover
names, but it must not directly select mutation targets.

- [ ] `tag` accepts multiple explicit repository names in one call.
- [ ] Bulk tag resolves repository node IDs in one batch, as the TUI does.
- [ ] Bulk tag returns one result per repository. A failure for one repository
      does not hide the results for other repositories.
- [ ] `unstar` accepts multiple explicit repository names.
- [ ] Bulk unstar shows the complete target list before mutation and requires
      confirmation.
- [ ] A non-interactive bulk unstar requires an explicit confirmation flag.
- [ ] No Filter, search term, stdin stream, wildcard, or implicit selection can
      choose bulk unstar targets.
- [ ] Bulk action JSON reports success or failure for each explicit target.
- [ ] Existing single-Star `tag` and `unstar` calls keep their behavior.

## Scope 3 — Operational JSON

Keep `ghstars status` offline. Put live API data behind a separate explicit
network call.

- [ ] `status --json` reports active Star count, Archived Star count, List
      count, Unclassified count, pending-edit count, Retriage Queue count, last
      sync time, and verify results.
- [ ] A separate CLI action returns the live API rate limit as JSON.
- [ ] The live rate-limit action does not run a full sync.
- [ ] `sync --json` reports the ordered sync stages and the final sync result in
      one valid JSON document.
- [ ] JSON sync output includes failed tag pushes and final Star and List
      counts.
- [ ] Human sync progress does not corrupt JSON output.
- [ ] Tests prove that `status` does not create a GitHub client or make a
      network call.

## Non-goals

- Do not expose TUI layouts, colours, keybindings, view state, or config-editor
  behavior through the CLI.
- Do not add a CLI equivalent for opening a repository in a browser.
- Do not let a query result directly trigger a destructive action.
- Do not add Folder or grid presentation to the CLI.

## Completion gate for ticket 14

Before ticket 14 starts, document each stable command, option, JSON schema, exit
code, and partial-failure rule. The agent skill must call these deterministic
interfaces. It must not reproduce discovery or mutation logic itself.
