# 0009 — Three-tier config split

## Status

accepted

## Implemented

done

## Context

ADR 0002 puts user-authored settings under `~/.ghstars/config/` and
machine-written data under `~/.ghstars/state/`. It says nothing about
how many files `config/` itself holds, or how a new setting picks one.

Before ticket 32, `config/` held two files: `export.toml` (ticket 10,
the export engine's schema) and `tui.toml` (ticket 21, the TUI's
settings). No file held a core setting outside export, and no file held
a CLI setting. Ticket 30 needs a configurable default row cap for the
CLI and had nowhere to put it, so it hardcoded the default instead.

`export.toml` sat oddly among the two: it configures `ghstars.core`, the
layer every other layer sits on top of, but its file was named and
loaded as if export were its own standalone concern, on equal footing
with the TUI. Nothing else in `ghstars.core` had a config file, so
`export.toml` was really the core tier's only member, wearing the wrong
name.

## Decision

### The three tiers

`config/` holds one file per layer:

- `ghstars.toml` — core-tier settings. Anything `ghstars.core` defines,
  or anything every layer above it would want, lives here.
- `cli.toml` — CLI-tier settings. A setting only the CLI reads lives
  here. No loader reads this file yet; ticket 30 adds the first one.
- `tui.toml` — TUI-tier settings, unchanged by this decision. Every
  field ticket 21/23/28 already put here stays here.

### The assignment rule

Apply this test to every new setting:

- Would every consumer of `ghstars.core` want it, not just one
  interface on top of it? Core. `ghstars.toml`.
- Would only the CLI ever read it? CLI. `cli.toml`.
- Would only the TUI ever read it? TUI. `tui.toml`.

One setting lives in exactly one of these three files, never two. Copy
this rule into `ghstars.cli.deps`, where a reader adding a path getter
for a new tier will find it, and into `ghstars.core.config`'s module
docstring, where a reader adding a table to `ghstars.toml` will find it.

### Relationship to ADR 0002

ADR 0002 already governs `config/` as a whole: TOML, plain-text,
git-diffable, stow-managed, and never written to by ghstars on the
user's behalf. This decision does not change any of that — it only
says how many files sit inside `config/` and which setting goes in
which one. A missing file still means every default applies, the same
rule `tui.toml` and the retired `export.toml` already followed.
`GHSTARS_HOME` (ticket 30) relocates all three files together, the same
way it relocates `state/`.

### Relationship to ADR 0008

ADR 0008 splits the TUI's own two files, `config/tui.toml` and
`state/tui-state.toml`, by a different test: version-controlled/
same-on-every-machine is config, "what the user last looked at" is
state. That test still governs everything inside the TUI tier. This
decision sits one level up: it decides which of ghstars' three
interfaces (core, CLI, TUI) a setting belongs to at all, before ADR
0008's config/state test ever applies. A TUI setting still goes through
both tests — first "TUI tier" (this decision), then "config or state"
(ADR 0008) — and neither test moves a field the other one placed.

### Folding `export.toml` into `ghstars.toml`

`export.toml`'s schema (`ExportEntry`/`ExportConfig`, ticket 10) is a
core concern under the rule above — every layer sits on `ghstars.core`,
and export selection lives in `ghstars.core.export`. It moves into the
`[export]` table of `ghstars.toml`, unchanged in shape. Only where it
loads from changed: `ghstars.core.config.load_core_config` replaces the
retired `ghstars.core.export.load_export_config`, and
`ghstars.cli.deps.get_core_config_path()` replaces the retired
`get_export_config_path()`.

This is a hard break, not a migration. No release has happened yet, so
there is no installed base to carry forward: ghstars does not read the
old `export.toml`, and does not ship a migrate command — ADR 0002
already forbids ghstars writing into `config/` on the user's behalf,
and a migrate command would do exactly that.

A leftover `export.toml` on disk (e.g. from a dotfiles repo checked out
before this decision) must not silently change behavior. ghstars warns
about it once per invocation, on stderr, rather than ignoring it
outright — the same "never guess, never go silent" principle a bad
config file already gets via `CoreConfigError`. It never reads the
file's contents.

## Consequences

- `ghstars.core.export.load_export_config` and `ExportConfigError` are
  retired. `ghstars.core.config.load_core_config` and `CoreConfigError`
  replace them; `ExportEntry`/`ExportConfig` (the schema) and
  `select_stars`/`run_export` (selection and writing) are unchanged.
- `ghstars.cli.deps.get_export_config_path()` is retired.
  `get_core_config_path()` and `get_cli_config_path()` replace it,
  alongside the existing `get_tui_config_path()`.
- `ghstars export`'s config now lives in the `[export]` table of
  `ghstars.toml`, documented in `docs/how-to/export.md`.
- Ticket 30's CLI-tier row cap has a home (`cli.toml`) once it lands.
  This decision does not add that setting itself.
