# Handoff

## Sources

Read these files before you change behavior:

| Source | Content |
| --- | --- |
| `.scratch/ghstars-v1/spec.md` | Product stories, storage layout, and non-goals. |
| `.scratch/ghstars-v1/issues/` | Acceptance criteria and implementation notes. |
| `docs/adr/` | Architecture decisions. |
| `CONTEXT.md` | Domain terms. |
| `docs/agents/issue-tracker.md` | Local issue workflow. |
| `docs/explanation/known-limitations.md` | Accepted limitations. |

## Current state

Ticket 23 is complete. The config editor opens with `g` or from the
Ctrl+P command palette. Esc validates and saves. The `x` key discards
edits. The fixed help stays visible while the form body scrolls.

## Follow-up work

- Replace each Layout column field with a two-pane chooser. Show
  Available and Selected columns. Use Space to move a column. Use
  Shift+J/K to reorder selected columns.
- Add h/j/k/l navigation to TUI DataTables. Keep text-input and modal
  keys unchanged.
- Review ticket 25 and its dependents. Retire Folder View Mode if
  filtering replaces its remaining use cases. Update the spec, README,
  CONTEXT, ADRs, and affected issues in that task.
- Reproduce the disappearing Star selection mark in a real terminal.
  Headless tests do not reproduce it.

## Safety

- Do not run a real sync without explicit approval.
- Do not run a real unstar or List mutation during development.
- Use an isolated state directory for an approved live test.
- Keep normal GitHub authentication separate from test state.

## Checks

Run focused tests, the full test suite, and diagnostics before handoff.
Regenerate `docs/adr/INDEX.md` with the ADR tool after an index-changing
ADR update. Do not edit the index by hand.
