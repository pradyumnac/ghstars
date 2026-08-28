# 14 — Accompanying agent skill (replaces `github-stars`)

**What to build:** Ship an agent skill with ghstars. Mirror the existing
`github-stars` skill structure. Document how agents use `ghstars.cli` for sync,
tag, retriage review, unstar, category rename or drain, status, export, and
diff.

When the agent notices relevant workflow friction, it tells the user directly
as a plain observation. It does not persist, deduplicate, or apply
observations.

This skill replaces `github-stars` when ghstars is stable. This ticket does not
decide how to retire the old skill in the AI-stowing system. Record that
question as a follow-up when work starts.

**Blocked by:** 30.

**Status:** ready-for-agent

- [ ] Skill documents the deterministic/agentic division of labor for sync,
      tag, retriage, unstar, category rename/drain, status, export, and diff
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
| `diff` | Scope 6 | Covered |
| `stars` | Scopes 1 and 2 | Covered |
| `facets` | Scope 1 | New command |
| `retriage` | None needed | Ready before ticket 30 |
| `category rename` / `drain` | None needed | Ready before ticket 30 |
| `export` | None needed | Ready before ticket 30 |

Ticket 14's own checklist names eight commands. Ticket 30 covers all eight, and
adds `facets`. Document `facets` too.

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

- [ ] Do not start until Scope 0's second review returns a go verdict. That
      review runs against the live account under an isolated `GHSTARS_HOME`,
      with the user's approval (Decision 24).
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
