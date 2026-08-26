# 0008 — TUI config and TUI state hold disjoint fields

## Status

accepted

## Implemented

done

## Context

ADR 0002 puts user-authored settings in `~/.ghstars/config/` and
machine-written session data in `~/.ghstars/state/`. Ticket 21 applied
that split to the TUI. It created `config/tui.toml` and
`state/tui-state.toml`.

Ticket 21 put `layout` in both files. `TuiConfig.layout` held a base
value. `TuiState.layout` held an optional override of that base. Two
files then held the same fact. A reader cannot tell which file wins.

Ticket 23 adds an editor for `tui.toml` inside the TUI. The editor must
show a field list. A field that lives in both files has no correct place
in that list. The split needs a rule before the editor is built.

Ticket 24 names clock visibility. More settings can follow. A rule must
decide where each one lands.

## Decision

### The rule

Apply this test to every new TUI field:

- A value the user wants under version control, or the same on every
  machine, is config. It belongs in `config/tui.toml`.
- A value that records what the user last looked at is state. It belongs
  in `state/tui-state.toml`.

One fact must never live in both files.

A definition and an active selection are two different facts. Config can
define the layout presets. State can record which preset is active now.
This is not a duplicate fact, so it does not break the rule.

Copy this test into the docstring of `TuiConfig` and `TuiState`.

### Config holds these fields

`config/tui.toml` holds:

- `keybindings` — an action name mapped to a key.
- `header_height`.
- `show_clock`.
- `category_colours` — a Category name mapped to a colour.
- `date_format`.
- `toast_timeout`.
- `ascii_only`.
- `default_filter`.
- `[layouts.compact]` and `[layouts.balanced]`. Each preset holds
  `columns`, `detail_pane_visible`, `row_height`, and
  `detail_pane_height`.
- `layout` — the preset to use on the first launch.

`columns` holds an ordered list. The list sets which columns show and in
what order.

Column names come from the `Star` model: Owner, Language, License,
Stars, Starred at, First seen, Membership, Fork, Follow, Archived,
Archived at, and Last checked. The Sel column and the Star column always
show. Description is not a column.

### State holds these fields

`state/tui-state.toml` holds:

- `layout` — the active preset.
- `sort_key`.
- `filter`.
- `detail_pane_visible` — a session override of the preset value. A
  layout switch resets this override.

No field in this list gets a config counterpart. The TUI never shows
these fields in the config editor.

### Keybindings

The user can rebind the 17 actions that `TuiApp.BINDINGS` declares.

The user cannot rebind `ctrl+q`, `ctrl+c`, `ctrl+p`, or `g`. `ctrl+c` is
a terminal convention. `ctrl+q` is the force-quit path. `ctrl+p` opens
the command palette. `g` opens the config editor directly. A config file
that names one of these keys fails validation.

The user cannot rebind a modal screen key. In the config editor, Esc
validates and saves a changed form. The `x` key discards the form. The
`q` key quits only from the main screen. Other modal screens keep Escape
and their own navigation keys.

### Config changes need a restart

ghstars applies `tui.toml` once, at launch. A saved change takes effect
on the next launch.

Two apply steps are not idempotent, which is why ghstars does not reapply
them in a running session:

- `_apply_keybinding_overrides` moves a key inside
  `self._bindings.key_to_bindings`. A second call runs against a map that
  the first call already changed.
- `_apply_colour_overrides` reads the active theme as its base. After the
  first call the active theme is already the overridden one, so a second
  call layers an override on an override.

The `z` key still switches the active layout during a session. That
switch selects between two presets that launch already loaded. It does
not reread the file, so the restart rule holds.

## Consequences

### Removed

- `TuiConfig.colours` and `TuiColours`. Ticket 28 forbids an application
  palette, so nothing replaces this field. The TUI uses the active
  Textual theme.
- `_apply_colour_overrides`.
- `TuiState.layout` as an override of `TuiConfig.layout`. State keeps
  `layout` as the active preset instead.
- `TuiConfig.grid_card_truncation`. Ticket 26 is retired because ghstars has
  no grid view.
- `TuiState.view_mode`. Ticket 25 is retired because the flat Star table and
  Filters cover the required navigation.

A `tui.toml` that holds a `[colours]` table fails to load. The error
names the removed table.

### Overrides ticket 28

Ticket 28 is done. This decision reverses two of its criteria.

**Category colour values.** Ticket 28 maps a Category to a Textual
semantic text role. This decision replaces the role with a named colour
from a fixed set.

The set must hold colours that reach 3:1 contrast on a light background
and on a dark background. Verify each colour on both before you ship it.
Ticket 28's other rule still holds: colour is never the only Category
cue, and the Category text stays visible. Ticket 28's stable digest still
picks the default for a Category the user has not set.

**Narrow terminals.** Ticket 28 hides lower-priority columns as the
terminal narrows, and forbids horizontal scrolling. This decision keeps
every configured column and scrolls the table instead.

The `_narrow` width check and its hardcoded 90-column threshold are
removed. The detail pane no longer hides itself on a narrow terminal. The
layout preset and the user's toggle control the pane.

### Rejected settings

These stay out of config:

| Setting | Reason |
| --- | --- |
| Rate-limit warning threshold | Belongs to the API client, not the TUI. |
| Sync page size | Not user facing. |
| `gh` subprocess timeout | Not user facing. |
| Recency filter boundaries | The current cutoffs already work. |
| Search debounce | Only matters on a very large account. |
| Star-count number format | Low value. |
| Description column | The detail pane already shows the description. |
| Grid card truncation | ghstars has no grid view. |
| View Mode | ghstars uses a flat Star table and Layout presets. |
| Auto-refresh interval | ADR 0006 makes every sync explicit. |
| Unstar confirmation toggle | A safety rail. Story 68 requires it. |
