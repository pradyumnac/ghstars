# Handoff

## Next work

Ticket 31 is done. Ticket 30 is in progress, worked sequentially per its own
execution note:

- Scope 3 (error contract) and Scope 6 (environment and history) — done,
  landed in commit `17508c2` ("issue #30 scope 3 done - wip commit mid
  session", 2026-08-27; the message undersold itself, Scope 6 shipped in the
  same commit). Independently re-verified against their acceptance criteria
  on 2026-08-28, not just the ticket's self-report: no gaps, full suite
  passed (373 passed).
- Scope 1 (discovery surface) — done, 2026-08-28. `ghstars list` now calls
  `core.discovery.query_stars()` for every Filter/search/sort/
  `--include-archived`; new `ghstars facets` command wraps
  `core.discovery.available_facets()`. See the ticket's own Scope 1
  checkboxes for the delivered-note detail.
- Scope 2 (output contract) — done, 2026-08-28. New `FIELD_REGISTRY["star_row"]`
  entry (`core/fields.py`, `StarRowFields`); `list`/`lists`/`retriage` all
  gained `--details` and now emit one `--json` envelope shape
  (`{"total", "offset", "limit", "rows"}` — Decision 19, a hard break from
  the old bare array, no deprecation shim); `list` gained `--limit`
  (default 50, `DEFAULT_LIST_LIMIT`) and `--offset`. Plain-text basic output
  is now an aligned table; `--details` text is a key-value block per record.
  `CONTEXT.md` records the field-set/ticket-14 coupling (Decision 9/18).
  See the ticket's own Scope 2 checkboxes for the delivered-note detail.

Full suite passes (398 passed — 12 new tests from Scope 1, 13 more from
Scope 2, across `tests/test_cli_list.py`, `tests/test_cli_lists.py`,
`tests/test_cli_facets.py`, `tests/test_fields.py`, `tests/test_cli.py`);
`ruff check` and `mypy src/` both clean.

Next up per the ticket's sequential execution order: **Scope 4** (explicit
bulk actions — `tag`/`unstar` take more than one repository name, bulk
`unstar` confirmation). It depends on ticket 31 Scope C, already delivered
(`bulk_tag_stars()`/`bulk_unstar_stars()` in `core/tagging.py`/`core/unstar.py`).
Scope 5 (operational JSON) has no ticket-31 dependency either and could run
before or after Scope 4 — the ticket's execution note only pins Scope 6 and
Scope 3 to run before everything else, which is already done.

See `.scratch/ghstars-v1/issues/30-cli-feature-parity-for-agent-use.md`
(unblocked) and `.scratch/ghstars-v1/issues/32-three-tier-config.md` (Scope 3
remaining, blocked on ticket 30) for open scopes. Both carry their own
checkbox state — check there, not here.

## Ticket 30 — parallel execution plan

Provisional. **It conflicts with ticket 30's own Execution note**, which says
work the scopes sequentially in one session. Reconcile the two before starting.
The ticket wins unless the user changes it.

The plan comes from a file-ownership analysis of `src/ghstars/cli/`. Two scopes
touch every command file, so they cannot run beside anything. Three scopes touch
disjoint command files, so they can.

### Wave 0 — serial, not parallel

Scope 6 first, then Scope 3. They overlap on `commands/diff.py`'s failure
calls, so they must not run together.

1. **Scope 6** — `cli/deps.py`, `commands/diff.py`, `git_diff.py`, ADR 0002.
   Delivers `GHSTARS_HOME`. Every later lane needs it for an isolated test
   home, and Scope 0's review needs it.
2. **Scope 3** — `cli/errors.py` plus every command's `except` block, and a new
   ADR at status `proposed`. Land the new error API *and* convert every call
   site, so wave 1 branches from a stable base. Also pre-land the shared
   envelope helper and the command-registration stubs in `cli/__init__.py`, or
   all three wave-1 lanes collide there.

### Wave 1 — three lanes in parallel

| Lane | Scope | Owns | Tests |
| --- | --- | --- | --- |
| A | 1 and 2 | `commands/list_lists.py`, `cli/__init__.py`, `core/fields.py`, new `facets` command | `test_cli.py`, new discovery-CLI test |
| B | 4 | `commands/tag.py`, `commands/unstar.py` | `test_unstar.py`, `test_tagging.py` |
| C | 5 | `commands/status.py`, `core/status.py`, `commands/sync.py`, new `ratelimit` command | `test_cli_status.py`, `test_sync.py`, `test_no_auto_sync.py` |

Scopes 1 and 2 stay in one lane. Both rewrite `list` and the shared renderer,
so splitting them creates a conflict, not a speed-up.

Merge order A, then B, then C. Run the full test suite at each merge.

### Wave 2 — serial

Ticket 32 Scope 3: move the hardcoded 50-row cap into `cli.toml`. It needs
lane A's cap to exist first.

### Wave 3 — serial, one worker

1. Scope 7 — write `docs/reference/cli.md`.
2. Scope 0 — the second review. It cannot be split. It runs against merged
   `main`, never a lane branch, and it needs live-account approval on the day.

### Cost

Serial order is 7 steps. This plan is 4 steps: wave 0 counts as 2. The saving
is wave 1 only. Every other step stays serial.

## Unscheduled follow-ups

No ticket covers these.

- Replace the Layout column text fields with a two-pane chooser.
- Add `h`/`j`/`k`/`l` navigation to TUI `DataTable` widgets without changing
  text-input or modal keys.
- Reproduce the disappearing Star-selection mark in a real terminal. Headless
  tests do not reproduce the problem.

## Safety

- Do not run a real sync without explicit approval.
- Do not run a real unstar or List mutation during development.
- Use an isolated state directory for an approved live test. Override `HOME` to
  get one; the ghstars home directory is hardcoded until ticket 30 adds
  `GHSTARS_HOME`.
- Keep normal GitHub authentication separate from test state.

## Checks

Run focused tests, the full test suite, and diagnostics before handoff.

## Task rail

_No unfinished Task tool work._
