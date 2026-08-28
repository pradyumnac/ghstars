# ghstars

A terminal-first CLI for classifying your GitHub starred repos into
GitHub's own Lists — github.com, your phone, and `ghstars` all stay in
sync.

## Install

```bash
uv tool install ghstars
```

## Authenticate

ghstars uses your existing `gh` CLI login. Reads (`sync`, `stars`,
`github-lists`) work on `gh`'s default scopes. `ghstars tag` also creates
GitHub Lists. That needs the `user` scope. Grant it once:

```bash
gh auth refresh -h github.com -s user
```

Without it, `ghstars tag` fails with a clear error. The error names
the missing scope. Nothing breaks silently.

## Use

```bash
ghstars --help
```

## Configure

`ghstars` auto-creates `~/.ghstars/config/` on every run. Taxonomy
definitions land with a later ticket. Export mappings go in the
`[export]` table of `~/.ghstars/config/ghstars.toml` — see
[`docs/how-to/export.md`](docs/how-to/export.md).

TUI settings go in `~/.ghstars/config/tui.toml`: keybindings, Category
colours, presentation settings, table columns, and Layout presets. A
missing file means every default applies.

Press `g` in the TUI to open the config editor. You can also select
**Edit config** from the Ctrl+P command palette. The form keeps its key
help visible while the fields scroll. Press Esc to validate and save a
changed form. Press `x` to discard all edits. An invalid form stays open
and shows an error. Restart `ghstars` after a save to apply the changes.

`~/.ghstars/state/tui-state.toml` holds what the TUI remembers between
sessions: the active layout, sort, Filter, and detail-pane visibility.
`ghstars` owns this file. Do not edit it by hand.

Both directories hold plain text, so you can stow `config/` into a
dotfiles repository. `ghstars` never runs `git` against either one.

## Manuals

Unix manual sources are in [`man/`](man/):

- `ghstars(1)` documents all commands.
- `ghstars-tui(1)` documents TUI controls.
- `ghstars-tui(5)` documents `tui.toml`.

## Develop

```bash
mise run install    # sync dependencies
mise run check      # format, lint, type-check, test
```

## Licence

MIT
