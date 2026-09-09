# Handoff

## Next work

Tickets 33 and 34 landed on 2026-09-09. The taxonomy is flat, the vocabulary
lives in config, and `ghstars doctor` reports the account against it. See
ADR 0005 for the model and `docs/reference/cli.md` for the repair loop.

**Ticket 14, the agent skill, is next and is now the largest open item.** This
session tripled its surface: the skill must cover `doctor`, `remote
bootstrap`, `remote rename-list` and `untag` alongside the commands ticket 30
delivered.

### Open decisions

1. Choose an Intent for each blessed Category with no List. `remote bootstrap`
   takes one Intent per run, and the missing Categories do not share one.
   `Example` takes `Reference` or `Learn`, never `Explore` (ADR 0005).
2. Decide whether a skill may write to `ghstars.toml`. ADR 0002 forbids
   *ghstars* writing there. A skill is not ghstars, so blessing a Category
   from the wizard needs a ruling. See ticket 34.
3. Plan the triage pass for the unclassified Stars. ghstars cannot classify
   them: it must never guess an Intent or a Category (ticket 03). The pass
   needs a method, not a command.

### Notes repository split

Resolved 2026-09-09. ghstars does not depend on the old notes path or on
`scripts/gh-stars.py`. The only reference is one historical line in
`core/status.py`'s docstring. The split cannot break this repository.

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
