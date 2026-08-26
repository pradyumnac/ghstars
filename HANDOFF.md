# Handoff

Use this file only for context that has no better home. Ticket files hold
acceptance criteria and implementation notes. The spec and the ADR index
hold design decisions. Remove a note after it moves to one of those
sources.

## Where the real context lives

Read these before you write code:

| Source | Holds |
| --- | --- |
| `.scratch/ghstars-v1/spec.md` | Stories 1-76, the state and config layout, non-goals. |
| `.scratch/ghstars-v1/issues/NN-*.md` | One ticket per unit of work. Acceptance criteria and comments. |
| `docs/adr/INDEX.md` | Every architectural decision. Generated — do not hand-edit. |
| `CONTEXT.md` | The glossary. Use its terms in code and in tickets. |
| `docs/agents/issue-tracker.md` | How tickets and triage labels work here. |
| `docs/explanation/known-limitations.md` | Accepted limitations. Do not re-report them as bugs. |

## Session baseline

Working tree is clean at `7fe2dd5`. `git log` holds what each commit
did; this file only holds what is not yet in a commit, a ticket, or an
ADR.

No task below has started. The prior session's work was documentation
(ADR 0008, ticket 23's rewrite) and two code-review fixes unrelated to
ticket 23 (`FilterScreen`'s clear-filter option, and two `except A, B:`
sites) — see ticket 27's Comments and `git log` for those, not this
file.

## Task rail

The harness Task list is authoritative during a session. Load this rail
into it at the start of a session, and write the rail back at the end.

Ticket 23. Run these in order — each one depends on the one above it.
`.scratch/ghstars-v1/issues/23-tui-in-app-config-editor.md` holds the
acceptance criteria for each scope. Read "Next work" below before you
start task 1.

- [ ] **1. Change the schema** (scope 1) — add the new fields, add the
      layout preset model, remove `TuiColours`. `tui/config.py`
- [ ] **2. Read the new schema in the app** (scope 1) — delete
      `_apply_colour_overrides`, read sizing from the active preset.
      `tui/app.py`
- [ ] **3. Render the configured columns** (scope 1) — `tui/app.py`
- [ ] **4. Scroll instead of hiding columns** (scope 3) — delete
      `_narrow`. Overrides ticket 28. `tui/app.py`
- [ ] **5. Named Category colours** (scope 2) — replace the semantic text
      roles, measure the contrast. Overrides ticket 28. `tui/app.py`,
      `tui/config.py`
- [ ] **6. Validate keybindings** (scope 4) — reject a reserved key, an
      unknown action, a bad key string, and a duplicate. `tui/config.py`
- [ ] **7. Apply the presentation fields** (scope 1) — date format,
      notification timeout, text-only glyphs, clock, default Filter.
      `tui/app.py`
- [ ] **8. Build the editor modal** (scope 5) — plus the two Ctrl+P
      entries. `tui/app.py`

## Next work: ticket 23

Ticket 23 is the next TUI ticket, and it now blocks tickets 24 and 26.
It sets the final `tui.toml` schema, so those two tickets cannot read
fields that ticket 23 has not defined yet.

Start here:

1. Read `docs/adr/0008-tui-config-and-state-are-disjoint.md`. It defines
   which fields are config, which are state, and the test for a new
   field.
2. Read `.scratch/ghstars-v1/issues/23-tui-in-app-config-editor.md`. It
   holds five scopes with acceptance criteria.
3. Read ticket 21's Comments for the code ticket 23 changes, then read
   its superseding note at the bottom for the parts that no longer hold.

Ticket 23 reverses two criteria in ticket 28, which is `done` and tested.
Read ticket 28's superseding note before you change its code. Replace its
tests for progressive column hiding and for semantic-role Category
colours. Keep its WCAG 2.2 rule: colour is never the only Category cue.

Write the tests first. `tests/test_tui_config.py` holds ticket 21's 16
tests and is the right place for the schema tests. `tests/test_tui.py`
holds the app-level tests.

### Traps in this ticket

These notes are not in the ticket or the ADR. Read them before you start
the task they name.

- Task 1 breaks `tui/app.py` at once, because `app.py` reads
  `_config.colours`, `_config.row_height`, and `_config.layout` today.
  The suite stays red until task 2 lands. Treat tasks 1 and 2 as
  one commit.
- Task 5 has no library for the contrast check. Measure each colour
  against a light background and a dark background by hand, and record
  the numbers in the ticket.
- Task 8 needs the whole schema settled, because the modal lists every
  field. Do not start it early.
- `grid_card_truncation` has no consumer in this ticket. Ticket 26 reads
  it. Define the field and leave it unused.

## Ticket status

- Ticket 27 is partial. Flat-view filters, search, sorting, license
  display, persistence, and explicit sync work. Folder integration waits
  for ticket 25.
- Unblocked now: 12, 23, 25.
- Ticket 24 and ticket 26 wait for ticket 23. Ticket 26 also waits for
  ticket 25.
- Story 47 has no ticket. Create one after ticket 14 defines how
  `gh-stars.py` and `github-stars` retire.
- Ticket 18 has no acceptance criteria. It needs a design decision first.

## Pending investigation

- The Star-list selection mark can disappear in a real terminal after the
  user presses the select key. Headless tests pass. Reproduce this in
  `ghstars tui` before you change code or create a ticket.

## Safety

- Do not run `sync` against the user's account without explicit
  permission.
- Do not run a real unstar or a real List mutation during development or
  tests.
- For an approved sync test, use an isolated state directory. Keep the
  normal GitHub authentication configuration separate. ADR 0002 and the
  sync command hold the storage paths.
- The test List `zzz-ghstars-verify-delete-me` still exists on the
  account. Do not delete it through development code.

## Development checks

- Use a worktree for a ticket-scoped change when parallel work is active.
- Run the ticket tests, the full test suite, and diagnostics before
  handoff.
- Update the ticket file and this note only when the spec, an ADR, or
  project documentation does not already hold the information.
- Regenerate the ADR index with the `adr-lifecycle` skill's
  `build_index.py --write`. Never hand-edit `docs/adr/INDEX.md`.
