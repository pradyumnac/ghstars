# 21 — TUI config foundation: tui.toml and tui-state.toml

**What to build:** ghstars reads `~/.ghstars/config/tui.toml` at TUI launch for keybinding overrides, header/row sizing, and the colour palette, and applies them before the first paint. It reads `~/.ghstars/state/tui-state.toml` at launch for the last View Mode, sort key, and active Filter, and writes that file back on quit. A missing file means every default applies, the same rule `load_export_config` already follows for `export.toml`.

This ticket adds `tomlkit` as a dependency — run a dependency-review pass first — and uses it for both files, so the config-editor ticket needs no second dependency pass.

Per the spec's "TUI config: two files, split by who writes them" note: `config/tui.toml` is user-authored, stow-managed dotfiles (ADR 0002); this ticket only reads it. `state/tui-state.toml` is machine-owned; this ticket reads and writes it freely.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `tomlkit` added to `pyproject.toml` after a dependency-review pass; `uv.lock` regenerated
- [ ] `config/tui.toml`, if present, overrides default keybindings, header height, row height, and colour palette; a missing file changes nothing
- [ ] `state/tui-state.toml` is read at launch (missing file → defaults) and written at quit, holding at least the last View Mode, sort key, and active Filter
- [ ] Hand-editing `tui.toml` to rebind a key and change row height, then relaunching, shows both changes take effect
- [ ] Changing View Mode, quitting, and relaunching restores the same View Mode from `tui-state.toml`
- [ ] ghstars never writes to `config/tui.toml` in this ticket — only `state/tui-state.toml` is machine-written here (ADR 0002)
