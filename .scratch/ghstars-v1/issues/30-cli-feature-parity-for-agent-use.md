# 30 — CLI agent contract

**What to build:** Turn the CLI into a stable interface for an agentic LLM.
Expose the core discovery query, explicit-name bulk actions, a machine-readable
error contract, and operational JSON. Keep presentation and TUI config out of
the CLI. Complete this ticket before ticket 14 defines the agent skill.

The last CLI-focused work added `status --json`, immediate `tag`, sync progress,
and shared unstar orchestration. Later TUI work added discovery filters, search,
sort, bulk tagging, collection counts, API status, and explicit sync state.
Ticket 31 moves all of that into `ghstars.core`. This ticket puts a CLI surface
on top of it.

**Blocked by:** None — ticket 31 is done. Every criterion below marked
"Depends on ticket 31 ..." must still be re-checked against the delivered
signatures in `.scratch/ghstars-v1/issues/31-core-consolidation.md`'s
"Delivered" notes before you rely on it.

**Status:** ready-for-agent

**Execution:** Work the scopes sequentially, in one session. Do not fan out
subagents. Run Scope 6 first, because Scope 0's second review depends on
`GHSTARS_HOME`.

## Scope 0 — Agent-consumption readiness review

The first review ran on 2026-08-27, against the CLI as it stood before ticket 31.
Its verdict was **no-go**. The findings and the decisions below are its output.
Repeat the review after all other scopes pass, and record the second verdict
here.

### First review — command inventory

| Command | State | Reason |
| --- | --- | --- |
| `status --json` | Needs work | Reports 5 of the 8 required fields. Offline, as designed. |
| `list --json` | Unsuitable | No Filter, search, Sort, limit, or pagination. |
| `lists --json` | Ready | Bounded output. |
| `retriage --json` | Ready | Bounded output. |
| `sync --json` | Needs work | Emits the final result only, never the ordered stages. |
| `tag --json` | Needs work | One repository per call. |
| `unstar --json` | Needs work | One repository per call. No confirmation. |
| `category rename` / `drain` | Ready | Reports migrated and skipped per target. |
| `export --json` | Ready | Bounded output. |
| `diff` | Needs work | Exit code carries no information. Argument surface is all of git. |
| `tui` | Not applicable | Interactive. |

### First review — blockers

1. `list` dumps the whole account. A 1525-Star account emits roughly 1 MB in one
   call. No agent can read that.
2. Discovery logic lives only in the TUI. Ticket 31 fixes this.
3. Bulk actions do not exist. `tag` and `unstar` each take one repository.
4. `--json` is abandoned on the error path. Every failure prints prose to
   standard error, whether or not the caller asked for JSON.
5. One exit code covers every failure. "No local record", "rate limit
   exceeded", "state lock held", "membership drift", and "network failure" are
   indistinguishable. An agent cannot decide whether to retry.
6. The TUI and the CLI disagree about Archived Stars. Ticket 31 fixes this.
7. `unstar` has no confirmation. An agent in a loop can drain the account one
   call at a time.
8. `list` returns List ids, never List names. Ticket 31 fixes this.
9. State has no environment override. The handoff safety rule requires an
   isolated state directory for a live test. No supported way exists.

### Decisions

| # | Decision |
| --- | --- |
| 1 | Every `unstar` requires confirmation. A non-interactive caller passes `--yes`. The agent can pass it. Ticket 14 carries the policy for when. |
| 2 | `list` caps rows at a default. `--limit` overrides it per call. |
| 3 | Under `--json`, a failure emits a JSON error object with a stable machine code. Exit codes separate a retryable failure from a terminal one. |
| 4 | Core excludes Archived Stars by default. `--include-archived` opts in. |
| 5 | Config tiers into three files. Ticket 32 owns this. |
| 6 | `export.toml` folds into `ghstars.toml`. Ticket 32 owns this. |
| 7 | Config tiering is ticket 32. This ticket ships a hardcoded default cap plus `--limit`, and reads `cli.toml` once ticket 32 lands. |
| 8 | Two field sets exist: basic and detailed. `--details` selects the detailed set. Both modes return the same fields; only the format differs. Basic text output is a table. |
| 9 | No schema version. A field-set change and a ticket 14 skill change land together. Record that coupling in `CONTEXT.md`. |
| 10 | `GHSTARS_HOME` overrides the state and config directory. |
| 11 | `diff` stays in the agent contract. It returns git's exit codes verbatim. The agent calls the zero-argument form and detects change by empty output. |
| 12 | Filters combine with AND. An agent can pass more than one. |
| 13 | `--fields` and `--details` both survive. `--fields` selects an arbitrary subset and overrides the named sets. |
| 14 | The default row cap is 50. `--limit` overrides it. Ticket 32 Scope 3 later moves the 50 into `cli.toml`. |
| 15 | Exit codes are 1 for a terminal failure, 3 for a retryable failure, and 4 for a partial failure. Typer keeps 2 for a usage error. |
| 16 | The basic Star set is `full_name`, `list_names`, `starred_at`, `stargazer_count`. The detailed set is every field on `Star` plus `list_names`. Nothing is subtracted. |
| 17 | `--details` prints a key-value record block in text mode, not a table. Decision 8's aligned-table rule applies to the basic set only. |
| 18 | The output of `list --json` changes twice: the field set narrows, and a bare array becomes an envelope. Take both as a hard break. Print no deprecation warning. No release exists, and ticket 13 has not started. |
| 19 | Every list-returning command emits the same envelope shape under `--json`: `total`, `offset`, `limit`, `rows`. `list`, `lists`, and `retriage` all use it. |
| 20 | `--offset` exists on `list` only. It slices local state after the sort. It never calls GitHub. `lists` and `retriage` return bounded output and get no cap and no offset. |
| 21 | Paging is deterministic for one state file. A `sync` between two paged calls shifts every later offset. Document that rule, and tell ticket 14 to finish paging before it syncs. |
| 22 | The `archived` field appears in the output only when the caller passes `--include-archived`. The default output never carries it. |
| 23 | The ADR for the JSON and exit-code contract stays at status `proposed`. Do not accept it in this ticket. Implement the contract as the ADR proposes it, and name every error code. |
| 24 | Scope 0's second review runs against the live account, under an isolated `GHSTARS_HOME`. Read paths only, no mutation. It needs the user's approval on the day. |
| 25 | The facet command is `ghstars facets`. It returns the six facet groups from `core.discovery.available_facets()`. |

### Second review

- [ ] Inventory each command again and classify it as ready, needs work, or
      unsuitable for agent use.
- [ ] Test the complete agent flow: inspect state, discover Stars, sync when
      required, classify one or many Stars, review Retriage Queue entries,
      unstar explicit Stars, export data, and inspect history through `diff`.
      Run it against the live account under an isolated `GHSTARS_HOME`
      (Decision 24). Use read paths only. Get the user's approval first --
      HANDOFF.md forbids a real sync without it.
- [ ] Check JSON schema stability, exit codes, standard output purity, standard
      error use, partial failures, and error messages.
- [ ] Check that large outputs are bounded and can be paged without losing a
      stable order.
- [ ] Check that every network call is explicit and every mutation names its
      targets.
- [ ] Check that a destructive action requires a confirmation contract that also
      works without a terminal.
- [ ] Measure the command count and the output size for the tested agent flows.
- [ ] Record a go or no-go verdict here. List every blocker and link each
      blocker to an acceptance criterion.
- [ ] Do not start ticket 14 until the final verdict is go.

## Scope 1 — Discovery surface

> Depends on ticket 31 Scope A. Re-check every criterion here against the
> delivered core query signature and Filter grammar. Update a criterion if the
> signature differs.

- [x] `ghstars list` exposes every core Filter as an option: Category, Intent,
      List, Language, License, Owner, Fork, Followed, Unclassified, and
      starred-date recency.

      **Delivered:** `list_cmd` in `cli/commands/list_lists.py` — repeatable
      `--category`/`--intent`/`--list`/`--language`/`--license`/`--owner`,
      plus boolean `--fork`/`--followed`/`--unclassified` and `--recent
      <window>`. Every option builds a `core.discovery` Filter string;
      `list_cmd` contains no Filter logic of its own.
- [x] More than one Filter can apply in one call. The CLI combines them with
      AND, through core.

      **Delivered:** every option appends to one `filters: list[str]` passed
      to `query_stars(..., filters=filters)`, which AND-combines
      (`core/discovery.py`, unchanged). Tested by
      `test_list_two_filters_and_combine` in `tests/test_cli_list.py`.
- [x] `ghstars list` exposes the core search.

      **Delivered:** `--search`, passed straight through to
      `query_stars(..., search=search)`.
- [x] `ghstars list` exposes every core Sort, in both directions.

      **Delivered:** `--sort`, validated against `core.discovery.SortMode`'s
      twelve values (`_SORT_MODES` in `list_lists.py`) before the call; an
      unrecognised value hard-fails via `fail()` with `CODE_INVALID_INPUT`
      rather than silently falling back, since `query_stars` itself would
      raise `ValueError` for an unknown `SortMode` cast.
- [x] `--include-archived` opts back into Archived Stars. The default excludes
      them.

      **Delivered:** `--include-archived`, passed to
      `query_stars(..., include_archived=include_archived)`.
- [x] The `archived` field appears in the output only when the caller passes
      `--include-archived` (Decision 22). Without the field, an Archived Star
      and an active Star look the same, and an agent tags an Archived Star and
      gets `StarArchivedError`.

      **Delivered:** `list_cmd` appends `"archived"` to the default field list
      only when `--include-archived` is set; an explicit `--fields archived`
      still works either way, since that is the caller's own choice. Tested
      by `test_list_include_archived_adds_the_archived_field_to_default_output`.
- [x] A command or an option returns the available facet values, so an agent can
      learn what it can filter on. A facet value comes from
      `core.discovery.available_facets()`: Categories, Intents, Lists,
      languages, licenses, and owners, all read from the user's own data.
- [x] Name the command `ghstars facets` (Decision 25). It supports `--json`
      like every other read command.

      **Delivered:** `cli/commands/facets.py`, new `ghstars facets` command,
      wraps `core.discovery.available_facets()` verbatim. `--json` emits one
      object with all six groups (Lists as full dumped `List` records, so an
      agent gets both `id` and `name` to pass to `--list`); text mode prints
      one labelled line per non-empty group.
- [x] `--json` output holds machine data only. Human status text goes to
      standard error, or does not print.

      **Delivered:** both `list --json` and `facets --json` emit exactly one
      JSON document to standard out and nothing else; `list` reuses the
      existing `cli._render_records` JSON path unchanged.
- [x] The CLI implements no Filter, Sort, or search rule of its own. It calls
      core.

      **Delivered:** `list_cmd` builds Filter-key strings and calls
      `query_stars()`/`available_facets()`; it contains no filtering, sorting,
      or search logic. Confirmed by reading `list_lists.py` and `facets.py`
      end to end — the only conditional logic outside filter-string assembly
      is the sort-mode validation and the `archived`-field default toggle,
      neither of which is a Filter/Sort/search rule.

## Scope 2 — Output contract

> Depends on ticket 31 Scope A and Scope D. Re-check every criterion here
> against the delivered field registry.

- [ ] Two field sets exist for each record type: basic and detailed. Basic is
      the default.
- [ ] The basic Star set is `full_name`, `list_names`, `starred_at`,
      `stargazer_count` (Decision 16). At the 50-row cap it costs about 6.1 KB
      per call, measured against the user's 1550-Star state.
- [ ] The detailed Star set is every field on `Star` plus `list_names`. It
      costs about 24.5 KB at the 50-row cap.
- [ ] Add a `"star_row"` entry to `FIELD_REGISTRY` for both sets. `fields.py`'s
      module docstring asks this ticket to make that call.
- [ ] `--details` selects the detailed set.
- [ ] JSON mode and text mode return the same fields for the same set. Only the
      format differs.
- [ ] Basic text output is an aligned table, not space-joined values. The
      shared renderer serves `list`, `lists`, and `retriage`, so all three get
      the table.
- [ ] `--details` prints a key-value record block in text mode, not a table
      (Decision 17). A 16-column table does not fit a terminal.
- [ ] `--fields` still selects an arbitrary subset, and overrides both named
      sets.
- [ ] A Star row carries its resolved List names. An agent never joins ids
      itself.
- [ ] `list` caps rows at 50. Hardcode the 50 in this ticket.
- [ ] `--limit` overrides the cap per call.
- [ ] `--offset` pages `list` only (Decision 20). It slices local state after
      the sort, and never calls GitHub.
- [ ] Under `--json`, `list`, `lists`, and `retriage` all emit one envelope
      shape: `total`, `offset`, `limit`, `rows` (Decision 19). A bounded
      command reports its own count in `total`.
- [ ] The break to `list --json` is hard: the field set narrows and the shape
      changes, with no deprecation warning (Decision 18).
- [ ] `--json`, `--fields`, and `--details` work with every discovery option.
- [ ] Pagination or the limit is deterministic. A repeated call returns the same
      rows in the same order.
- [ ] Document that paging is stable only while local state is (Decision 21). A
      `sync` between two paged calls shifts every later offset.
- [ ] Record in `CONTEXT.md` that a field-set change and a ticket 14 agent-skill
      change must land together. There is no schema version.
- [ ] Leave the `export`, `list`, and `retriage` basic sets as they are. This
      ticket changes the `star` entry only.

## Scope 3 — Error contract

No dependency on ticket 31.

- [x] Under `--json`, a failure emits a JSON error object on standard error. The
      object holds a stable machine code, a human message, and the failing
      target where one exists.

      **Delivered:** `fail()` in `cli/errors.py`. Every command's `except`
      block calls it with an explicit `code=` and `json_output=`; see ADR
      0010 for the full call-site table.
- [x] Define the machine codes. Cover at least: no local record, Star Archived,
      List-membership drift, tag push failed, rate limit exceeded, state lock
      held, network failure, invalid input, and unknown field.

      **Delivered:** all nine, plus `tool_unavailable` for `diff`'s
      git-binary-missing path (`cli/errors.py` `CODE_*` constants).
- [x] Exit codes separate a retryable failure from a terminal one: 1 is
      terminal, 3 is retryable, 4 is a partial failure (Decision 15). Three
      flat codes, no reserved ranges. The agent reads the JSON machine code for
      detail.
- [x] Typer's exit code 2 stays for a usage error.
- [ ] A bulk call that fails for some targets and succeeds for others reports
      each target and exits with a documented partial-failure code.

      `EXIT_PARTIAL` (4) is defined in `cli/errors.py`; no command emits it
      yet — bulk `tag`/`unstar` land in Scope 4.
- [x] Write an ADR for the CLI JSON and exit-code contract. Record the machine
      codes, the three exit codes, and the rule that there is no schema
      version. Leave the ADR at status `proposed` (Decision 23). Do not accept
      it in this ticket. Implement the contract exactly as the ADR proposes
      it.

      **Delivered:** `docs/adr/0010-cli-json-and-exit-code-contract.md`,
      status `proposed`.

## Scope 4 — Explicit bulk actions

> Depends on ticket 31 Scope C. Re-check every criterion here against the
> delivered bulk-tag and bulk-unstar signatures.

Use explicit repository names for every bulk mutation. A Filter can discover
names, but it must never select a mutation target.

- [ ] `tag` accepts more than one explicit repository name in one call.
- [ ] `unstar` accepts more than one explicit repository name in one call.
- [ ] Both bulk commands return one result per repository. A failure for one
      repository never hides the result for another.
- [ ] Every `unstar` requires confirmation, single or bulk. This reverses the
      earlier rule that single-Star `unstar` keeps its behavior.
- [ ] A non-interactive `unstar` requires an explicit `--yes` flag.
- [ ] Bulk unstar prints the complete target list before it mutates anything.
- [ ] No Filter, search term, standard input stream, wildcard, or implicit
      selection can choose a mutation target.
- [ ] Bulk action JSON reports success or failure for each explicit target.
- [ ] Single-Star `tag` keeps its current behavior.

## Scope 5 — Operational JSON

No dependency on ticket 31.

Keep `ghstars status` offline. Put live API data behind a separate explicit
network call.

- [ ] `status --json` reports active Star count, Archived Star count, List
      count, Unclassified count, pending-edit count, Retriage Queue count, last
      sync time, and verify results. `StatusReport` carries 5 of the 8 today,
      so this widens the model.
- [ ] "Pending-edit count" counts Stars whose `pending_list_ids` is not null.
      Record that it stays zero while ADR 0004 keeps pending staging dormant.
- [ ] A separate CLI action returns the live API rate limit as JSON.
- [ ] The live rate-limit action does not run a full sync.
- [ ] `sync --json` reports the ordered sync stages and the final sync result in
      one valid JSON document.
- [ ] JSON sync output includes failed tag pushes and the final Star and List
      counts.
- [ ] Human sync progress does not corrupt JSON output.
- [ ] A test proves that `status` does not create a GitHub client or make a
      network call.

## Scope 6 — Environment and history

No dependency on ticket 31.

- [x] `GHSTARS_HOME` overrides the hardcoded home directory for state and
      config. A live test can then use an isolated directory.

      **Delivered:** `get_ghstars_home()` in `cli/deps.py` reads the
      `GHSTARS_HOME` environment variable and falls back to
      `DEFAULT_GHSTARS_HOME`. Every path getter in that module calls it.
- [x] Rename the existing module constant `GHSTARS_HOME` in `cli/deps.py` to
      `DEFAULT_GHSTARS_HOME`. The constant and the environment variable must
      not share a name.
- [x] Amend ADR 0002. It states one fixed `~/.ghstars/` tree, and the
      environment override changes that.
- [x] Bare `ghstars diff` shows a summary instead of a full patch. This changes
      the human default.

      **Delivered:** bare `diff` runs `git diff --stat`.
- [x] `--patch` shows the full patch.
- [x] `diff` returns git's exit codes verbatim. Document them. The exit code
      never says whether anything changed.

      **Documented:** in `diff_cmd`'s docstring (`cli/commands/diff.py`) --
      `git diff`/`git diff --stat` always exit 0, whether or not anything
      changed; full documentation lands in Scope 7's `docs/reference/cli.md`.
- [x] The agent contract for `diff` is the zero-argument form only. The agent
      detects a change by empty output.
- [x] Argument pass-through to git stays available for a human caller, and stays
      outside the agent contract.

## Scope 7 — Completion gate for ticket 14

- [ ] Write `docs/reference/cli.md`. Document every stable command, option,
      field set, JSON schema, machine error code, exit code, and
      partial-failure rule.
- [ ] Re-read every criterion in this ticket that references ticket 31. Confirm
      each one matches the delivered core signature.
- [ ] The agent skill must call these deterministic interfaces. It must not
      reproduce discovery or mutation logic itself.

## Non-goals

- Do not expose TUI layouts, colours, keybindings, view state, or config-editor
  behavior through the CLI.
- Do not add a CLI equivalent for opening a repository in a browser.
- Do not let a query result directly trigger a destructive action.
- Do not add Folder or grid presentation to the CLI.
- Do not add discovery, Sort, search, or mutation-orchestration logic to the
  CLI. Ticket 31 owns all of it.
- Do not add a config file or a config field. Ticket 32 owns config.
