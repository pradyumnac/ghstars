# 32 — Three-tier config

**What to build:** Split ghstars configuration into three files, one per layer.
Core concerns live in `ghstars.toml`. CLI concerns live in `cli.toml`. TUI
concerns stay in `tui.toml`. Fold the existing `export.toml` into
`ghstars.toml`, because export is a core concern.

`config/` holds two files today: `export.toml` and `tui.toml`. No file holds a
core setting, and no file holds a CLI setting. Ticket 30 needs a configurable
default row cap and has nowhere to put it, so it hardcodes the default instead.
This ticket gives every layer a home.

**Blocked by:** None — can start immediately. This ticket does not gate ticket
30 or ticket 31.

**Status:** ready-for-agent

## Scope 1 — The three tiers

- [ ] Create `config/ghstars.toml` for core settings.
- [ ] Create `config/cli.toml` for CLI settings.
- [ ] `config/tui.toml` keeps every TUI setting. Do not move a TUI field.
- [ ] Write the rule that decides which file a new setting lands in. Copy the
      rule into each loader's docstring.
- [ ] One setting must never live in two files.
- [ ] ghstars never writes into `config/` on the user's behalf. ADR 0002 holds.
- [ ] A missing file means every default applies. This matches how `tui.toml`
      and `export.toml` already behave.
- [ ] `GHSTARS_HOME` from ticket 30 relocates all three files.

## Scope 2 — Fold export into core config

Nothing has released yet. Ticket 13 has not started. Take the hard break.

- [ ] Move the `export.toml` schema into `ghstars.toml` under `[export]`.
- [ ] Delete the `export.toml` load path. Do not read the old file.
- [ ] Do not write a migration. Do not add a migrate command. ADR 0002 forbids
      ghstars writing into `config/`.
- [ ] A leftover `export.toml` on disk must not change behavior. Decide whether
      to warn about it or ignore it, and apply one answer.
- [ ] Rewrite `docs/how-to/export.md` for the new location.
- [ ] Amend ticket 10 to point here.

## Scope 3 — Adopt the CLI tier

- [ ] Move ticket 30's hardcoded default row cap into `cli.toml`.
- [ ] `--limit` still overrides the configured value per call.
- [ ] Update `docs/reference/cli.md` from ticket 30 with the config key and its
      precedence.
- [ ] Record the precedence rule: a CLI option beats a config value, and a
      config value beats the built-in default.

## Scope 4 — Decision record

- [ ] Write an ADR for the three-tier split. State the rule that assigns a
      setting to a tier.
- [ ] State how the split relates to ADR 0002, which puts user-authored settings
      in `config/` and machine-written data in `state/`.
- [ ] State how the split relates to ADR 0008, which keeps TUI config and TUI
      state disjoint. That rule still holds inside the TUI tier.
- [ ] Record the `export.toml` hard break and the reason: no release has
      happened.

## Non-goals

- Do not move a TUI field out of `tui.toml`.
- Do not add a config editor for `ghstars.toml` or `cli.toml`. The TUI editor
  covers `tui.toml` only.
- Do not let ghstars write into `config/`.
- Do not add a new CLI command or option beyond the config source change.
