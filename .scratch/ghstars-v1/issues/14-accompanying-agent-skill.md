# 14 — Accompanying agent skill (replaces `github-stars`)

**What to build:** Ship an agent skill with ghstars. Mirror the existing
`github-stars` skill structure. Cover every stable, non-interactive CLI
operation: status, rate limit, sync, facet and List inspection, Star discovery,
tag and retag, retriage review, unstar, Category rename or drain, export, and
diff.

When the agent notices relevant workflow friction, it tells the user directly
as a plain observation. It does not persist, deduplicate, or apply
observations.

This skill replaces `github-stars` when ghstars is stable. This ticket does not
decide how to retire the old skill in the AI-stowing system. Record that
question as a follow-up when work starts.

**Blocked by:** 30.

**Status:** ready-for-agent

- [ ] Skill documents the deterministic/agentic division of labor for status,
      rate limit, sync, facets, Star and List discovery, tag/retag, retriage,
      unstar, Category rename/drain, export, and diff
- [ ] Skill tells the user about relevant workflow friction as a plain observation
- [ ] Skill does not persist, deduplicate, or apply observations
- [ ] Skill structure mirrors the existing `github-stars` skill
- [ ] Skill is vendored the same way `github-stars` is today
- [ ] Decide and carry out the `github-stars` → `ghstars` retirement. This is
      the last step of this ticket. See "Retirement order" below. The original
      wording deferred this as a follow-up; the user reassigned it here.

## Notes from ticket 30 (append-only)

Ticket 30 froze the CLI agent contract. Everything below constrains this
ticket. Do not restate a ticket 30 decision here; read it there and follow it.
Source: `.scratch/ghstars-v1/issues/30-cli-feature-parity-for-agent-use.md`,
Decisions 1 to 25.

### Command coverage after ticket 30

| Command | Ticket 30 scope | State |
| --- | --- | --- |
| `sync` | Scope 5 | Covered |
| `tag` | Scope 4 | Covered |
| `unstar` | Scope 4 | Covered |
| `status` | Scope 5 | Covered |
| `ratelimit` | Scope 5 | Covered |
| `diff` | Scope 6 | Covered |
| `stars` | Scopes 1 and 2 | Covered |
| `github-lists` | Scope 2 | Covered |
| `facets` | Scope 1 | New command |
| `retriage` | None needed | Ready before ticket 30 |
| `category rename` / `drain` | None needed | Ready before ticket 30 |
| `export` | None needed | Ready before ticket 30 |

The skill targets every stable, non-interactive CLI operation. It does not call
`ghstars tui`, use human-only `diff` arguments, or reproduce TUI presentation.

## Agent workflow parity matrix

This matrix is the scope ledger for ticket 14. “Planned” means the skill must
document and use the operation. “Excluded” means the omission is intentional,
not a parity defect. Update this matrix whenever the CLI, TUI, or skill changes.

| Workflow | Agent skill | CLI | TUI | Parity note |
| --- | --- | --- | --- | --- |
| Inspect local health and counts | Planned | Full: `status --json` | Partial: chrome counts and sync/API state | The agent also gets verify, pending-edit, and Retriage Queue fields. |
| Inspect live API rate limit | Planned | Full: `ratelimit --json` | Full: refresh action and status chrome | Network call is always explicit. |
| Sync Stars and Lists | Planned | Full: `sync --json` | Full: explicit `y` action | No surface syncs automatically. |
| Learn valid facet values | Planned | Full: `facets --json` | Partial: values appear inside Filter pickers | The agent never hardcodes the user's vocabulary. |
| Discover and page Stars | Planned | Full: `stars --json` | Full: interactive table | Agent and CLI are bounded; the TUI scrolls local state. |
| Combine Filters | Planned | Full: repeated Filters combine with AND | Partial: one active Filter plus search | Agent capability is broader than the TUI here. |
| Search name and description | Planned | Full: `stars --search` | Full: `/` search | Both call the shared discovery core. |
| Sort discovery results | Planned | Full: 12 directional modes | Partial: six cycling presets | Agent capability is broader than the TUI here. |
| Inspect Archived Stars | Planned when requested | Full: `--include-archived` | Not supported | TUI discovery intentionally shows active Stars only. |
| Inspect Star details or selected fields | Planned | Full: `--details` / `--fields` | Full: Detail pane and configured columns | The skill always requests fields useful for its task. |
| Inspect GitHub Lists | Planned | Full: `github-lists --json` | Full: Lists overview | CLI and agent can select exact fields. |
| Select mutation targets | Planned: explicit names | Full: positional and repeatable `--repo` | Full: cursor or interactive selection | Filters and search never become mutation selectors. |
| Tag or retag one Star | Planned | Full: `tag` | Full: tag picker | Both use the shared tagging core. |
| Bulk tag or retag Stars | Planned | Full: repeated `--repo` | Full: selected Stars | Both report per-target failures. |
| Unstar one Star | Planned with policy and `--yes` | Full | Full: confirmation screen | The skill owns the policy for asking the user first. |
| Bulk unstar explicit Stars | Planned with policy and `--yes` | Full: repeated `--repo` | Excluded | TUI deliberately limits unstar to one Star per confirmation. |
| Review Retriage Queue | Planned | Full: `retriage --json` | Not supported | Administrative workflow, not interactive discovery. |
| Rename or drain a Category | Planned | Full: `category rename` / `drain` | Not supported | Administrative bulk operation with drift reporting. |
| Export configured data | Planned | Full: `export --json` | Not supported | Config-driven downstream integration. |
| Inspect state history | Planned: zero-argument form | Full: `diff`; extra arguments are human-only | Not supported | The agent detects changes from empty or non-empty output. |
| Open a repository in a browser | Excluded | Not supported | Full: `o` action | Interactive convenience; ticket 30 explicitly excludes it from CLI parity. |
| Edit TUI config and presentation | Excluded | Not supported | Full: editor, Layout, Detail pane, keybindings | Presentation state is outside the agent contract. |
| Report workflow friction | Planned | Not a CLI operation | Not a TUI operation | The skill reports an observation and does not persist or apply it. |

### Parity conclusion

The ticket 14 target is full parity with the stable non-interactive CLI
contract, not literal parity with every TUI action. The agent will cover all
CLI data, discovery, mutation, operational, export, and history workflows. It
will exceed the TUI for combined Filters, directional sorts, Archived history,
bulk unstar, Retriage Queue review, Category operations, export, and diff. It
will intentionally omit browser opening, interactive selection, Layouts, the
Detail-pane UI, keybindings, and the TUI config editor.

### Rules the skill must follow

- [ ] The skill never uses the CLI default field set. The basic Star set is
      `full_name`, `list_names`, `starred_at`, `stargazer_count` (Decision 16).
      It holds no `description` and no `language`, so it cannot answer a
      classification question. Every discovery call the skill makes passes
      `--details` or `--fields`.
- [ ] The skill learns valid Filter values from `ghstars facets` (Decision 25),
      never from a hardcoded vocabulary. A Category exists only if the user's
      own Lists define it.
- [ ] The skill finishes paging before it calls `sync` (Decision 21). A `sync`
      between two paged calls shifts every later offset.
- [ ] The skill reads `total` from the `--json` envelope to know when to stop
      paging (Decision 19). The envelope is `total`, `offset`, `limit`, `rows`.
- [ ] The skill respects the 50-row cap and raises it with `--limit` only when
      it has a reason (Decision 14).
- [ ] The skill passes `--include-archived` when it needs to see Archived
      Stars, and knows that the `archived` field appears only then
      (Decision 22). Without the flag it must never assume a row is active by
      the absence of the field.
- [ ] The skill never tags an Archived Star. `tag_star` raises
      `StarArchivedError`, and CONTEXT.md keeps Archived separate from Retired.
- [ ] The skill branches on exit codes: 1 terminal, 3 retryable, 4 partial
      failure, 2 usage error (Decision 15). It reads the JSON error object's
      machine code for detail.
- [ ] The skill never lets a Filter or a search term choose a mutation target.
      Every mutation names its repositories explicitly (ticket 30, Scope 4).
- [ ] The skill passes `--yes` to `unstar` because it has no terminal
      (Decision 1). This ticket owns the policy for when an unstar is allowed
      at all.
- [ ] The skill calls `ghstars status` before it decides whether a `sync` is
      worth the round trip. `status` is offline by design.

### Coupling rule

There is no schema version (Decision 9). A change to a CLI field set and the
matching change to this skill must land in the same commit. Ticket 30 Scope 2
records that rule in `CONTEXT.md`.

### Gates on this ticket

- [x] Do not start until Scope 0's second review returns a go verdict. The
      approved live review returned go on 2026-08-28 under an isolated
      `GHSTARS_HOME` (Decision 24).
- [ ] Read `docs/reference/cli.md` from ticket 30 Scope 7 first. It is the
      source for every command, option, field set, error code, and exit code.
- [ ] The ADR for the JSON and exit-code contract stays at status `proposed`
      (Decision 23). Write this skill against the proposed contract, and
      re-check it if the ADR changes before it is accepted.

### Retirement order

The retirement of the `github-stars` skill is this ticket's call, and it is the
**last step**. Do every other criterion first. Reason: `github-stars` is the
only working way to answer a Stars question until the new skill ships and
proves itself. Retire it after the new skill covers every command in the table
above, not before.

Order:

1. Write the new skill against the ticket 30 contract.
2. Vendor it the same way `github-stars` is vendored today.
3. Use it for real Stars work, and confirm it answers what `github-stars`
   answered.
4. Only then decide how `github-stars` retires from the AI-stowing system, and
   record that decision in this file.
