# Handoff

## Start here

Read these sources before you change behavior:

| Source | Use |
| --- | --- |
| `.scratch/ghstars-v1/spec.md` | Product stories and non-goals. |
| `.scratch/ghstars-v1/issues/` | Acceptance criteria and ticket state. |
| `docs/adr/` | Accepted design decisions. |
| `CONTEXT.md` | Domain terms. |
| `docs/explanation/known-limitations.md` | Accepted limits. |

## Next work

### 1. Establish the agent CLI contract

Start ticket 30. Run its Scope 0 readiness review before you add parity
features. The review must give a go or no-go verdict for agentic LLM use.

Then implement the shared discovery query, explicit-name bulk actions, and
operational JSON. Keep discovery rules in `ghstars.core`; the TUI and CLI must
not have separate filter implementations.

Ticket 14 is blocked until ticket 30 passes its completion gate. Do not write
the agent skill against unstable commands or JSON schemas.

### 2. Complete the remaining product work

| Ticket | State | Next action |
| --- | --- | --- |
| 12 | Ready | Add the local nudge store. It is required before ticket 14. |
| 24 | Retired | No further work is planned under this ticket. |
| 18 | Retired | Empty List membership always means Unclassified. |
| 13 | Ready | Start after tickets 12 and 14 complete. |
| 15 | Ready | Start after ticket 13. |

## Retired scope

Tickets 25 and 26 are retired. ghstars has no Folder or grid view. The flat
Star table uses Layout presets. A Layout changes density and visible columns;
it does not change navigation or Star arrangement.

Ticket 27 is complete because its only pending requirement was Filter behavior
inside the retired Folder view.

## Unscheduled follow-ups

- Replace the Layout column text fields with a two-pane chooser.
- Add `h`/`j`/`k`/`l` navigation to TUI `DataTable` widgets without changing
  text-input or modal keys.
- Reproduce the disappearing Star-selection mark in a real terminal. Headless
  tests do not reproduce the problem.

## Safety

- Do not run a real sync without explicit approval.
- Do not run a real unstar or List mutation during development.
- Use an isolated state directory for an approved live test.
- Keep normal GitHub authentication separate from test state.

## Checks

Run focused tests, the full test suite, and diagnostics before handoff.
Regenerate `docs/adr/INDEX.md` with the ADR tool after an index-changing ADR
update. Do not edit the index by hand.
