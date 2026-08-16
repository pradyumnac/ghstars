# ghstars

TODO: one sentence.

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

See `docs/reference/configuration.md`.

## Develop

```bash
mise run install    # sync dependencies
mise run check      # format, lint, type-check, test
```

## Licence

MIT
