# 21 — TUI config foundation: tui.toml and tui-state.toml

**What to build:** ghstars reads `~/.ghstars/config/tui.toml` at TUI launch for keybinding overrides, header and row sizing, and the colour palette. It reads `~/.ghstars/state/tui-state.toml` at launch for the active Layout, sort key, and Filter, and writes that file on quit. A missing file means every default applies, the same rule `load_export_config` already follows for `export.toml`.

This ticket adds `tomlkit` as a dependency — run a dependency-review pass first — and uses it for both files, so the config-editor ticket needs no second dependency pass.

Per the spec's "TUI config: two files, split by who writes them" note: `config/tui.toml` is user-authored, stow-managed dotfiles (ADR 0002); this ticket only reads it. `state/tui-state.toml` is machine-owned; this ticket reads and writes it freely.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] `tomlkit` added to `pyproject.toml` after a dependency-review pass; `uv.lock` regenerated
- [x] `config/tui.toml`, if present, overrides default keybindings, header height, row height, and colour palette; a missing file changes nothing
- [x] `state/tui-state.toml` is read at launch (missing file → defaults) and written at quit, holding the active Layout, sort key, and Filter
- [x] Hand-editing `tui.toml` to rebind a key and change row height, then relaunching, shows both changes take effect
- [x] Changing Layout, quitting, and relaunching restores the same Layout from `tui-state.toml`
- [x] ghstars never writes to `config/tui.toml` in this ticket — only `state/tui-state.toml` is machine-written here (ADR 0002)

## Comments

- New module `src/ghstars/tui/config.py`: `TuiConfig`/`TuiColours` (read
  via `load_tui_config`, mirrors `load_export_config`'s missing-file-is-
  defaults / present-but-invalid-raises rule) and `TuiState` (read via
  `load_tui_state`, but a corrupt state file falls back to defaults
  rather than blocking launch — it's machine-written, not hand-authored
  config, so failing loudly over it would be user-hostile) plus
  `save_tui_state` (atomic write, via the same `atomic_write` helper
  `StateStore`/`export.py` already share).
- `TuiApp.__init__` now takes optional `config_path`/`state_path`
  (defaulting to siblings of the `StateStore`'s own directory so tests
  and this module need no `ghstars.cli` import); the real CLI entry
  point (`ghstars.cli.commands.tui`) passes explicit paths from two new
  `ghstars.cli.deps` getters, `get_tui_config_path()` /
  `get_tui_state_path()`, following the same explicit-path pattern
  `get_export_config_path()` already set.
- Keybinding overrides rebuild `self._bindings` from `BINDINGS` with
  each overridden action's key swapped, via Textual's own
  `Binding.make_bindings()`/`BindingsMap` — composes with the existing
  static `BINDINGS` list rather than replacing the mechanism, and an
  override naming an unknown action is silently inert (no
  `action_<name>` to dispatch to), not a hard error.
- Colour overrides go through Textual's own theme system
  (`App.register_theme`/`App.theme`), layered on top of the currently
  active theme rather than a fixed baseline, so a user who already
  picked a light/dark base theme elsewhere doesn't have that clobbered
  by an unrelated override.
- `view_mode` on `TuiState` is a stub, per the ticket's own guidance:
  there is no View Mode switcher yet (ticket 25 builds it). It defaults
  to `"list"`, is loaded/saved like every other state field, and a test
  (`test_tui_app_restores_view_mode_across_relaunch`) exercises the
  round trip by mutating `app._state.view_mode` directly — standing in
  for what a future switcher's action will do. Nothing in this ticket
  lets a user actually change it.
- "Header height"/"row height" map to `DataTable`'s own
  `header_height` constructor param and per-row `height` on
  `add_row()` (the star table's header row vs. its data rows) — the
  most literal reading of the spec's "header/row sizing" phrase given
  the widgets actually in play, not the top `Header` clock bar.
- Code review (medium effort) caught a real bug: the first cut of
  `_apply_keybinding_overrides` rebuilt `self._bindings` from
  `TuiApp.BINDINGS` alone, which silently dropped every App-level
  binding TuiApp itself never declares -- `ctrl+q` force-quit,
  `ctrl+c`, and the command palette's `ctrl+p` -- the moment a user
  configured even one `[keybindings]` override. Fixed by mutating the
  already-merged `self._bindings.key_to_bindings` in place instead,
  moving only the key(s) bound to an overridden action and leaving
  everything else untouched. Covered by a new regression test,
  `test_keybinding_override_preserves_inherited_app_bindings`.
- Tests: `tests/test_tui_config.py`, 16 new tests — missing-file
  defaults and invalid-file errors for both `load_tui_config` and
  `load_tui_state`, a save/load round trip (including that `None`
  fields are omitted, not written as empty strings), and `TuiApp`
  integration tests for keybinding override, header/row height,
  colour override, the config-file-never-written guarantee, and the
  View Mode persistence round trip. Full suite: 222 passed. `ruff
  check` and `mypy src` both clean.
- Avoided ticket 20's `RateLimitBar`/`_fetch_rate_limit` region and
  ticket 22's compose/detail-pane scope entirely — only touched
  `__init__`, `compose()`'s `DataTable(...)` line, `_refresh_table()`'s
  `add_row(...)` call, and added `action_quit`/two `_apply_*` helper
  methods.

**2026-08-26, superseded in part by tickets 23 and 25 and ADR 0008.** The
comments above describe the schema this ticket shipped. The current schema
removes the unused `view_mode` state field. These parts change:

- `TuiColours` and `_apply_colour_overrides` are removed. Ticket 28
  forbids an application palette. Nothing replaces them.
- `TuiState.layout` is no longer an override of `TuiConfig.layout`.
  Config defines the layout presets. State records the active preset.
- `category_colours` no longer maps a Category to a Textual semantic text
  role. It maps to a named colour from a fixed set.

Read ADR 0008 before you use this ticket's comments as a description of
the current schema.
