# 23 — In-TUI config editor and the final config schema

**What to build:** the final `tui.toml` schema, and a modal screen that
edits it from inside the TUI. Read ADR 0008 first. It defines which
fields are config, which are state, and why. Spec stories 5, 60, 61, 62,
69, 70, 71.

This ticket both changes the schema and builds the editor. Ticket 21
shipped a partial schema. Ticket 24 and ticket 26 each name a setting
that no file holds yet. One ticket lands all of them, so the editor
never ships against a schema that is about to move.

`config/tui.toml` is stow-managed dotfiles (ADR 0002). ghstars writes it
only when the user saves. An unasked-for rewrite looks like unrelated
churn in the user's dotfiles repository.

**Blocked by:** 21 (done).

**Status:** ready-for-agent

## Scope 1 — The config schema

Add these fields to `TuiConfig`:

- `date_format` — replaces the hardcoded `%d-%b-%Y` in `_format_date`.
- `toast_timeout` — replaces the hardcoded `timeout=8`.
- `ascii_only` — draws text markers in place of the glyphs at
  `tui/app.py:77-78` and the status icons.
- `grid_card_truncation` — the character limit ticket 26 needs.
- `default_filter` — the Filter to apply on a first launch.
- `show_clock` — the clock ticket 24 names.
- `[layouts.compact]` and `[layouts.balanced]`. Each preset holds
  `columns`, `detail_pane_visible`, `row_height`, and
  `detail_pane_height`.

Keep `keybindings`, `header_height`, `category_colours`, and `layout`.

`header_height` and `show_clock` stay top-level fields. Ticket 24 reads
both.

- [ ] `columns` holds an ordered list of column names. The order sets the
      column order.
- [ ] The column names are Owner, Language, License, Stars, Starred at,
      First seen, Membership, Fork, Follow, Archived, Archived at, and
      Last checked. The Sel column and the Star column always show.
- [ ] `detail_pane_visible`, `row_height`, and `detail_pane_height` read
      from the active preset, not from the top level.
- [ ] `header_height` stays a top-level field.
- [ ] A `tui.toml` that holds a `[colours]` table fails to load. The
      error names the removed table and tells the user that ghstars now
      uses the active Textual theme.
- [ ] `TuiColours` and `_apply_colour_overrides` are removed.
- [ ] The docstrings of `TuiConfig` and `TuiState` hold the config and
      state test from ADR 0008.

## Scope 2 — Category colours

This scope overrides ticket 28. Read ADR 0008's "Overrides ticket 28"
section first.

- [ ] `category_colours` maps a Category name to a named colour from a
      fixed set. It no longer maps to a Textual semantic text role.
- [ ] Every colour in the set reaches 3:1 contrast on a light background
      and on a dark background. Record the measured values.
- [ ] A stable digest of the Category name picks the default colour. This
      keeps ticket 28's behaviour. A collision is acceptable.
- [ ] The Category text stays visible. Colour is never the only Category
      cue. This keeps ticket 28's WCAG 2.2 rule.
- [ ] Render General Lists in a muted colour. Do not hash an empty
      Category.

## Scope 3 — Narrow terminals

This scope overrides ticket 28. Read ADR 0008 first.

- [ ] The table keeps every configured column and scrolls horizontally
      when the columns do not fit.
- [ ] The `_narrow` check and its hardcoded 90-column threshold are
      removed.
- [ ] The layout preset and the user's toggle control the detail pane.
      Terminal width no longer hides the pane.
- [ ] Replace the ticket 28 tests that cover progressive column hiding.

## Scope 4 — Keybindings

- [ ] The user can rebind the 17 actions in `TuiApp.BINDINGS`.
- [ ] A config that names `ctrl+q`, `ctrl+c`, or `ctrl+p` fails
      validation with a clear error.
- [ ] An unknown action name fails validation. Ticket 21 made it a silent
      no-op.
- [ ] An unparseable key string fails validation.
- [ ] Two actions bound to the same key fail validation. This includes a
      collision with a default the user did not override.
- [ ] Modal screen keys stay fixed.

## Scope 5 — The editor

- [ ] A Ctrl+P "Edit config" entry opens a modal that lists every field
      in Scope 1.
- [ ] The modal reads the values on disk, not the values in memory.
- [ ] Keybindings show as one row per action with a text field for the
      key.
- [ ] Category colours show as add and remove rows with a colour picker.
- [ ] Columns show as an ordered add and remove list, one list per
      layout preset.
- [ ] Save blocks on any validation error and marks the field. The editor
      never writes a file that fails to load.
- [ ] Save writes `tui.toml` through `tomlkit`. A round trip that changes
      nothing reproduces the same comments and key order.
- [ ] Save writes only `config/tui.toml`. It never writes
      `state/tui-state.toml`.
- [ ] Save writes only the fields the user changed. Every other field
      appears as a comment that names its default.
- [ ] Save shows a toast that tells the user to restart.
- [ ] Cancel discards the edits and leaves the file unchanged.
- [ ] A Ctrl+P "Show config path" entry prints the path.

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
