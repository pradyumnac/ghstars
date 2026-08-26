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

Working tree is clean at `2d90e21`. `git log` holds what each commit
did; this file only holds what is not yet in a commit, a ticket, or an
ADR.

No task below has started. The prior session's work was documentation
(ADR 0008, ticket 23's rewrite) and two code-review fixes unrelated to
ticket 23 (`FilterScreen`'s clear-filter option, and two `except A, B:`
sites) — see ticket 27's Comments and `git log` for those, not this
file.

## Task rail

This file holds the rail. This session has no harness Task list, so the
rail lives here. Update it as each task lands.

Ticket 23. `.scratch/ghstars-v1/issues/23-tui-in-app-config-editor.md`
holds the acceptance criteria for each scope. Read "Next work" below
before you start task 1.

### Foundation — blocks every other task

Land tasks 1 and 2 in one commit. `tui/app.py` reads
`_config.colours`, `_config.row_height`, and `_config.header_height`
today, so the suite stays red between the two tasks.

- [ ] **1. Change the schema** (scope 1) — add the new fields, add the
      layout preset model, remove `TuiColours`. `tui/config.py`
- [ ] **2. Read the new schema in the app** (scope 1) — delete
      `_apply_colour_overrides`, read sizing from the active preset.
      `tui/app.py`

### Three independent lanes

Each lane depends on the foundation. No lane depends on another lane.
Run the lanes in any order in one session. To run them as concurrent
agents, give each lane its own worktree, because all three edit
`tui/app.py`.

**Lane A — the table.** Task 3 blocks tasks 4 and 7. Tasks 4 and 7 are
independent of each other.

- [ ] **3. Render the configured columns** (scope 1) — `tui/app.py`
- [ ] **4. Scroll instead of hiding columns** (scope 3) — delete
      `_narrow`, `on_resize`, and the 90-column threshold. Overrides
      ticket 28. `tui/app.py`
- [ ] **7. Apply the presentation fields** (scope 1) — date format,
      notification timeout, text-only glyphs, clock, default Filter.
      `tui/app.py`

**Lane B — colour.**

- [ ] **5. Named Category colours** (scope 2) — replace the semantic text
      roles, measure the contrast. Overrides ticket 28. `tui/app.py`,
      `tui/config.py`

**Lane C — keybindings.**

- [ ] **6. Validate keybindings** (scope 4) — reject a reserved key, an
      unknown action, a bad key string, and a duplicate. `tui/config.py`

Lane A edits `_configure_table_columns`, `_refresh_table`, and
`on_resize`. Lane B edits `_category_role`, `_styled_category`, and
`_membership_chip`. Lane C edits `_apply_keybinding_overrides` and adds
a validator to `tui/config.py`. The three sets do not overlap.

### Last task

- [ ] **8. Build the editor modal** (scope 5) — plus the two Ctrl+P
      entries. `tui/app.py`

Task 8 is serial. The modal lists every field, so the schema must be
final first.

### Tests to delete or rewrite

| Test | Action | Task |
| --- | --- | --- |
| `test_tui.py:922 test_layout_density_and_narrow_columns` | Delete | 4 |
| `test_tui_config.py:287 test_tui_app_applies_colour_override` | Delete | 1 |
| `test_tui_config.py:85 test_load_tui_config_rejects_unknown_category_colour_role` | Rewrite for named colours | 5 |
| `test_tui.py:84 test_category_override_colours_membership_without_hiding_text` | Rewrite. Keep the WCAG assertion. | 5 |

### Decisions from the 2026-08-26 review

The ticket and ADR 0008 leave these four points open. The user settled
them. Record each one in the ticket or the ADR as the task lands.

- **The named colour set.** Neither the ticket, ADR 0008, nor the spec
  names the colours. Propose an eight-colour set from the bright ANSI
  names, measure each colour on a light background and a dark
  background, record the numbers in ticket 23, and get approval before
  task 5 writes code.
- **`show_clock` renders in this ticket.** Task 7 adds a clock `Static`
  to `#title-row`. `compose()` has no Textual `Header` today. Add a
  comment to ticket 24 that the widget already exists.
- **`default_filter` applies whenever `state.filter` is `None`.** A
  Filter that the user clears with `x` returns on the next launch.
  Config overrules state here. ADR 0008 does not cover this case, so
  record it in the ADR as an exception.
- **The editor preserves the file.** `tomlkit` edits the document in
  place. User comments and key order survive a save. Write the
  default-naming comments only when ghstars creates `tui.toml` from
  nothing.

### Cross-checks that passed

- `TuiApp.BINDINGS` holds 17 actions. ADR 0008's count is correct.
- Every column name in scope 1 maps to a field on the `Star` model.
- Ticket 24 and ticket 26 read the scope 1 fields. Neither ticket
  defines one.
- `tui/config.py:140` uses `except TOMLKitError, ValidationError:`. PEP
  758 makes this form valid, and `pyproject.toml` sets
  `requires-python = ">=3.14"`. This line is correct.

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

- Task 5 has no library for the contrast check. Measure each colour
  against a light background and a dark background by hand, and record
  the numbers in the ticket.
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
