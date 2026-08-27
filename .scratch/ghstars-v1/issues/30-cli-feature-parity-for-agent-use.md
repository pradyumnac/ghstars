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

### Second review

- [ ] Inventory each command again and classify it as ready, needs work, or
      unsuitable for agent use.
- [ ] Test the complete agent flow: inspect state, discover Stars, sync when
      required, classify one or many Stars, review Retriage Queue entries,
      unstar explicit Stars, export data, and inspect history through `diff`.
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

- [ ] `ghstars list` exposes every core Filter as an option: Category, Intent,
      List, Language, License, Owner, Fork, Followed, Unclassified, and
      starred-date recency.
- [ ] More than one Filter can apply in one call. The CLI combines them with
      AND, through core.
- [ ] `ghstars list` exposes the core search.
- [ ] `ghstars list` exposes every core Sort, in both directions.
- [ ] `--include-archived` opts back into Archived Stars. The default excludes
      them.
- [ ] A command or an option returns the available facet values, so an agent can
      learn what it can filter on.
- [ ] `--json` output holds machine data only. Human status text goes to
      standard error, or does not print.
- [ ] The CLI implements no Filter, Sort, or search rule of its own. It calls
      core.

## Scope 2 — Output contract

> Depends on ticket 31 Scope A and Scope D. Re-check every criterion here
> against the delivered field registry.

- [ ] Two field sets exist for each record type: basic and detailed. Basic is
      the default.
- [ ] `--details` selects the detailed set.
- [ ] JSON mode and text mode return the same fields for the same set. Only the
      format differs.
- [ ] Basic text output is an aligned table, not space-joined values.
- [ ] `--fields` still selects an arbitrary subset, and overrides both named
      sets.
- [ ] A Star row carries its resolved List names. An agent never joins ids
      itself.
- [ ] `list` applies a default row cap. Hardcode the default in this ticket.
- [ ] `--limit` overrides the cap per call.
- [ ] `--json`, `--fields`, and `--details` work with every discovery option.
- [ ] Pagination or the limit is deterministic. A repeated call returns the same
      rows in the same order.
- [ ] Record in `CONTEXT.md` that a field-set change and a ticket 14 agent-skill
      change must land together. There is no schema version.

## Scope 3 — Error contract

No dependency on ticket 31.

- [ ] Under `--json`, a failure emits a JSON error object on standard error. The
      object holds a stable machine code, a human message, and the failing
      target where one exists.
- [ ] Define the machine codes. Cover at least: no local record, Star Archived,
      List-membership drift, tag push failed, rate limit exceeded, state lock
      held, network failure, invalid input, and unknown field.
- [ ] Exit codes separate a retryable failure from a terminal one. Reserve a
      documented range for each class.
- [ ] Typer's exit code 2 stays for a usage error.
- [ ] A bulk call that fails for some targets and succeeds for others reports
      each target and exits with a documented partial-failure code.
- [ ] Write an ADR for the CLI JSON and exit-code contract. Record the machine
      codes, the exit-code ranges, and the rule that there is no schema version.

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
      sync time, and verify results.
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

- [ ] `GHSTARS_HOME` overrides the hardcoded home directory for state and
      config. A live test can then use an isolated directory.
- [ ] Bare `ghstars diff` shows a summary instead of a full patch. This changes
      the human default.
- [ ] `--patch` shows the full patch.
- [ ] `diff` returns git's exit codes verbatim. Document them. The exit code
      never says whether anything changed.
- [ ] The agent contract for `diff` is the zero-argument form only. The agent
      detects a change by empty output.
- [ ] Argument pass-through to git stays available for a human caller, and stays
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
