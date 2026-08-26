# 23 — In-TUI config editor and the final config schema

**What to build:** the final `tui.toml` schema, and a modal screen that
edits it from inside the TUI. Read ADR 0008 first. It defines which
fields are config, which are state, and why. Spec stories 5, 60, 61, 62,
69, 70, 71.

This ticket changes the schema and builds the editor. Ticket 21 shipped a
partial schema. Ticket 24 names a setting that no file holds yet. This ticket
lands it before the editor ships.

`config/tui.toml` is stow-managed dotfiles (ADR 0002). ghstars writes it
only when the user saves. An unasked-for rewrite looks like unrelated
churn in the user's dotfiles repository.

**Blocked by:** 21 (done).

**Status:** done

## Scope 1 — The config schema

Add these fields to `TuiConfig`:

- `date_format` — replaces the hardcoded `%d-%b-%Y` in `_format_date`.
- `toast_timeout` — replaces the hardcoded `timeout=8`.
- `ascii_only` — draws text markers in place of the glyphs at
  `tui/app.py:77-78` and the status icons.
- `default_filter` — the Filter to apply on a first launch.
- `show_clock` — the clock ticket 24 names.
- `[layouts.compact]` and `[layouts.balanced]`. Each preset holds
  `columns`, `detail_pane_visible`, `row_height`, and
  `detail_pane_height`.

Keep `keybindings`, `header_height`, `category_colours`, and `layout`.

`header_height` and `show_clock` stay top-level fields. Ticket 24 reads
both.

- [x] `columns` holds an ordered list of column names. The order sets the
      column order.
- [x] The column names are Owner, Language, License, Stars, Starred at,
      First seen, Membership, Fork, Follow, Archived, Archived at, and
      Last checked. The Sel column and the Star column always show.
- [x] `detail_pane_visible`, `row_height`, and `detail_pane_height` read
      from the active preset, not from the top level.
- [x] `header_height` stays a top-level field.
- [x] A `tui.toml` that holds a `[colours]` table fails to load. The
      error names the removed table and tells the user that ghstars now
      uses the active Textual theme.
- [x] `TuiColours` and `_apply_colour_overrides` are removed.
- [x] The docstrings of `TuiConfig` and `TuiState` hold the config and
      state test from ADR 0008.

## Scope 2 — Category colours

This scope overrides ticket 28. Read ADR 0008's "Overrides ticket 28"
section first.

- [x] `category_colours` maps a Category name to a named colour from a
      fixed set. It no longer maps to a Textual semantic text role.
- [x] Every colour in the set reaches 3:1 contrast on a light background
      and on a dark background. Record the measured values.
- [x] A stable digest of the Category name picks the default colour. This
      keeps ticket 28's behaviour. A collision is acceptable.
- [x] The Category text stays visible. Colour is never the only Category
      cue. This keeps ticket 28's WCAG 2.2 rule.
- [x] Render General Lists in a muted colour. Do not hash an empty
      Category.

## Scope 3 — Narrow terminals

This scope overrides ticket 28. Read ADR 0008 first.

- [x] The table keeps every configured column and scrolls horizontally
      when the columns do not fit.
- [x] The `_narrow` check and its hardcoded 90-column threshold are
      removed.
- [x] The layout preset and the user's toggle control the detail pane.
      Terminal width no longer hides the pane.
- [x] Replace the ticket 28 tests that cover progressive column hiding.

## Scope 4 — Keybindings

- [x] The user can rebind the 17 actions in `TuiApp.BINDINGS`.
- [x] A config that names `ctrl+q`, `ctrl+c`, `ctrl+p`, or `g` fails
      validation with a clear error.
- [x] An unknown action name fails validation. Ticket 21 made it a silent
      no-op.
- [x] An unparseable key string fails validation.
- [x] Two actions bound to the same key fail validation. This includes a
      collision with a default the user did not override.
- [x] Modal screen keys stay fixed.

## Scope 5 — The editor

- [x] The `g` key opens a modal that lists every field in Scope 1.
- [x] A Ctrl+P "Edit config" entry opens the same modal.
- [x] The modal reads the values on disk, not the values in memory.
- [x] Keybindings show as the last section, with one text field per
      action.
- [x] Category colours show as add and remove rows with a colour picker.
- [x] Columns show as an ordered add and remove list, one list per
      layout preset.
- [x] Esc validates a changed form. A validation error keeps the editor
      open, shows a notification, and prevents the write.
- [x] Save writes `tui.toml` through `tomlkit`. A round trip that changes
      nothing reproduces the same comments and key order.
- [x] Save writes only `config/tui.toml`. It never writes
      `state/tui-state.toml`.
- [x] Save writes only the fields the user changed. Every other field
      appears as a comment that names its default.
- [x] A save shows a toast that tells the user to restart.
- [x] The `x` key discards edits and leaves the file unchanged.
- [x] The `q` key quits only from the main screen.
- [x] The form body scrolls while the Esc Save and `x` Discard help stays
      visible.
- [x] Boolean fields use Yes and No selectors. Initial Layout uses a
      Compact and Balanced selector.
- [x] A Ctrl+P "Show config path" entry prints the path.

## Out of scope

- **Live apply.** A saved change takes effect on the next launch. ADR
  0008 records why `_apply_keybinding_overrides` and
  `_apply_colour_overrides` cannot run twice in one session.
- **A "Reload config" Ctrl+P entry.** Nothing applies live, so a reload
  entry would report a change that the user cannot see. The original
  ticket listed this entry. Do not build it.
- **A recovery path for a broken file.** `load_tui_config` still raises
  and stops the launch. The user repairs a broken `tui.toml` in an
  external editor.
- **A named application theme.** Ticket 28 forbids one. ADR 0008 keeps
  that rule.

## Comments

**2026-08-26, scope set by a grilling session.** The session settled the
config and state split, the field list, the keybinding scope, and the two
ticket 28 overrides. ADR 0008 records the decisions and the rejected
settings. The session also produced a research pass over the codebase for
hardcoded values that deserve a config field. Scope 1's new fields come
from that pass.

**2026-08-26, Scope 2 landed: the Category colour set.**

`category_colours` now maps a Category name to one of eight named
colours: red, orange, yellow, green, cyan, blue, magenta, and violet. An
unknown name fails validation and the error names both the bad value and
the whole set.

No single hex clears 3:1 on both polarities. A light theme bottoms out at
`$panel` #D0D0D0 (relative luminance 0.60) and a dark theme tops out at
`$panel` #242F38 (0.028); the two limits leave no overlapping band. Each
colour therefore ships two hex values, and the TUI selects the table that
matches the active Textual theme.

Measured WCAG 2.1 contrast against the worst-case background of each
polarity:

| Colour  | Light hex | vs #D0D0D0 | Dark hex | vs #242F38 |
| ------- | --------- | ---------- | -------- | ---------- |
| red     | #B3261E   | 4.24       | #FF8A80  | 5.98       |
| orange  | #8F4700   | 4.44       | #FFB870  | 8.02       |
| yellow  | #6E5600   | 4.55       | #EBD26A  | 9.07       |
| green   | #1F6B36   | 4.24       | #7FD69A  | 7.79       |
| cyan    | #00595F   | 5.25       | #5FD6DC  | 7.89       |
| blue    | #1A56C4   | 4.29       | #8AB4FF  | 6.53       |
| magenta | #A81E80   | 4.31       | #F79AD9  | 6.88       |
| violet  | #5B3FCB   | 4.51       | #B9A6FF  | 6.47       |

Every value also clears 3:1 on the other backgrounds of its polarity
(#FFFFFF and #E0E0E0; #121212 and #1E1E1E).
`test_every_category_colour_clears_three_to_one_contrast` recomputes the
whole table from the shipped hex values, so a later edit that breaks the
guarantee fails the suite.

Ticket 28's other rules stand: a digest of the Category name picks the
default, a collision is acceptable, General Lists stay muted, an empty
Category is never hashed, and the Category text is always visible.

**2026-08-26, complete.** All five scopes are implemented in commits
`ae2d3e0`, `163f827`, `ee2e17a`, `8f35273`, and `1e92b73`. The final
commit completed the in-app editor and the documentation.

Verification from the final implementation: `uv run pytest`, `uv run ruff
format --check .`, `uv run ruff check .`, and `uv run mypy src tests` passed.

**2026-08-26, scope update.** Ticket 26 is retired. The unused
`grid_card_truncation` field is removed from the schema and editor.
