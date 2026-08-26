# ghstars

A terminal-first CLI for classifying your GitHub starred repos into
GitHub's own Lists — github.com, your phone, and `ghstars` all stay in
sync.

## Install

```bash
uv tool install ghstars
```

## Authenticate

ghstars uses your existing `gh` CLI login. Reads (`sync`, `list`,
`lists`) work on `gh`'s default scopes. `ghstars tag` also creates
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
definitions land with a later ticket. Export mappings go in
`~/.ghstars/config/export.toml` — see
[`docs/how-to/export.md`](docs/how-to/export.md).

TUI settings go in `~/.ghstars/config/tui.toml`: keybindings, Category
colours, the table columns, and the layout presets. A missing file means
every default applies. `ghstars` writes this file only when you save an
edit from the TUI. A saved change takes effect on the next launch.

`~/.ghstars/state/tui-state.toml` holds what the TUI remembers between
sessions: the active layout, sort, Filter, and detail-pane visibility.
`ghstars` owns this file. Do not edit it by hand.

Both directories hold plain text, so you can stow `config/` into a
dotfiles repository. `ghstars` never runs `git` against either one.

## Develop

```bash
mise run install    # sync dependencies
mise run check      # format, lint, type-check, test
```

## Licence

MIT
