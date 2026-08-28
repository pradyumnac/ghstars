# Handoff

## Next work

Tickets 30 and 31 are done. Ticket 30's Scope 0 second review returned go on
2026-08-28, so ticket 14 may start.

- Scope 3 (error contract) and Scope 6 (environment and history) — done,
  landed in commit `17508c2` ("issue #30 scope 3 done - wip commit mid
  session", 2026-08-27; the message undersold itself, Scope 6 shipped in the
  same commit). Independently re-verified against their acceptance criteria
  on 2026-08-28, not just the ticket's self-report: no gaps, full suite
  passed (373 passed).
- Scope 1 (discovery surface) — done, 2026-08-28. `ghstars stars` now calls
  `core.discovery.query_stars()` for every Filter/search/sort/
  `--include-archived`; new `ghstars facets` command wraps
  `core.discovery.available_facets()`. See the ticket's own Scope 1
  checkboxes for the delivered-note detail.
- Scope 2 (output contract) — done, 2026-08-28. New `FIELD_REGISTRY["star_row"]`
  entry (`core/fields.py`, `StarRowFields`); `stars`/`github-lists`/`retriage` all
  gained `--details` and now emit one `--json` envelope shape
  (`{"total", "offset", "limit", "rows"}` — Decision 19, a hard break from
  the old bare array, no deprecation shim); `stars` gained `--limit`
  (default 50, `DEFAULT_LIST_LIMIT`) and `--offset`. Plain-text basic output
  is now an aligned table; `--details` text is a key-value block per record.
  `CONTEXT.md` records the field-set/ticket-14 coupling (Decision 9/18).
  See the ticket's own Scope 2 checkboxes for the delivered-note detail.
- Scope 4 (explicit bulk actions) — done, 2026-08-28. `tag`/`unstar` both
  gained a repeatable `--repo` option for extra targets, layered on
  `bulk_tag_stars()`/`bulk_unstar_stars()` (ticket 31 Scope C); single-target
  `tag` keeps its exact prior code path and JSON shape untouched. `unstar`
  now requires `--yes` unconditionally, single or bulk — no interactive
  prompt at all, since a tty-gated prompt would fail Scope 0's "works
  without a terminal" criterion, so `--yes` is the whole confirmation
  contract. Bulk JSON is `{"targets", "results": [...]}` with exit `0`/
  `EXIT_PARTIAL`(4), `EXIT_RETRYABLE`(3), or `EXIT_TERMINAL`(1), based on
  the bulk outcome.
  See the ticket's own Scope 4 checkboxes for the delivered-note detail.

- Scope 5 (operational JSON) — done, 2026-08-28. `StatusReport`
  (`core/status.py`) widened from 5 to 8 fields: `active_star_count`,
  `archived_star_count`, `list_count`, `pending_edit_count` added
  alongside the existing `last_sync_at`/`unclassified_count`/
  `retriage_queue_count`/`verify_ok`/`verify_problems`; `status` stays
  offline (`test_status_never_creates_a_github_client`). New `ghstars
  ratelimit` command (`cli/commands/ratelimit.py`) wraps
  `GitHubClient.check_rate_limit()` alone, never a full `sync()`. `sync
  --json` now emits `{"stages": [...], "star_count", "list_count",
  "failed_tag_pushes"}` — `sync_cmd` records every `on_stage` label into a
  list and spreads it alongside the existing `SyncResult` fields; human
  progress (spinner/`--debug` lines) still goes to stderr only. See the
  ticket's own Scope 5 checkboxes for the delivered-note detail.

The full suite passes (429 tests), including the CLI contract fixes.
Ruff and mypy also pass.

- Scope 7 (completion gate) — done, 2026-08-28. `docs/reference/cli.md`
  documents every stable command, option, field set, JSON schema,
  machine error code, exit code, and the partial-failure rule. Every
  ticket-31-referencing criterion in ticket 30 was re-checked against
  the delivered core signatures (`query_stars`, `available_facets`,
  `bulk_tag_stars`, `bulk_unstar_stars`) — no discrepancy found. The
  flagged command-name clash was resolved: `list` → `stars`, `lists` →
  `github-lists` (both renamed, not one — user's call; ticket 30
  Decision 26). Full suite, Ruff, and mypy passed after the rename. See the
  ticket's own Scope 7 checkboxes for
  the delivered-note detail.

Ticket 30's approved live review used an isolated `GHSTARS_HOME` and made no
GitHub mutation. It verified 1,550 Stars, 8 Lists, bounded deterministic pages,
JSON purity, validation errors, explicit network calls, unstar confirmation,
and local-only history inspection. The detailed measurements and command
inventory are in ticket 30's "Live review result" section.

Next up: **ticket 14**, the accompanying agent skill. Ticket 32 Scope 3 is also
unblocked. Each ticket carries its own checklist and status.

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
- Use an isolated state directory for an approved live test. Set
  `GHSTARS_HOME` to get one.
- Keep normal GitHub authentication separate from test state.

## Checks

Run focused tests, the full test suite, and diagnostics before handoff.

## Task rail

*No unfinished Task tool work.*
