# 23 — In-TUI config editor

**What to build:** a modal screen to view and edit `tui.toml` settings (keybindings, sizing, colour palette) from inside the TUI, with an explicit Save that writes the file via `tomlkit`, preserving the user's comments and key order. `config/tui.toml` is stow-managed dotfiles (ADR 0002); an unasked-for rewrite must never look like unrelated churn. Adds three Ctrl+P entries: "Edit config", "Show config path", "Reload config". Spec stories 5 (Ctrl+P), 70.

**Blocked by:** 21.

**Status:** ready-for-agent

- [ ] A Ctrl+P "Edit config" entry opens a modal listing every setting ticket 21 reads from `tui.toml`
- [ ] Save writes `tui.toml` via `tomlkit`; a round-trip (load, change nothing, save) reproduces the same comments and key order
- [ ] Save writes only `config/tui.toml`, never `state/tui-state.toml`
- [ ] Cancel discards edits and leaves the file untouched
- [ ] Ctrl+P "Show config path" and "Reload config" both work without opening the editor
