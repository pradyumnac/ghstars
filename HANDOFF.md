# Handoff

## Next work

Start ticket 31 (`.scratch/ghstars-v1/issues/31-core-consolidation.md`). It is
the only unblocked ticket on the critical path. Order: 31, 30, 14, 13, 15.
Ticket 32 is independent and gates nothing.

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
