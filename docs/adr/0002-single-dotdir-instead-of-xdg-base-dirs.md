# 0002 — Single ~/.ghstars/ directory instead of XDG base dirs

## Status

accepted

## Implemented

in-progress

## Context

Most modern CLI tools split config/data/state across `$XDG_CONFIG_HOME`, `$XDG_DATA_HOME`, and `$XDG_STATE_HOME`. ghstars deliberately doesn't: everything lives under one `~/.ghstars/` tree (`config/`, `state/`, `runtime/`).

The user manages dotfiles with GNU Stow and keeps config in plain-text, git-diffable formats specifically so they can be symlinked into a dotfiles repo. A single directory is trivial to stow; three directories scattered across the XDG hierarchy are not. `config/` and `state/` use TOML/YAML for this reason — `runtime/` (caches, nudge files) is the one subtree that's fine to stay untracked.

`ensure_config_dir()` in `cli/deps.py` creates `~/.ghstars/config/` on every CLI run, before any command runs. The directory starts empty — no ticket has defined its file content yet. The create step is a no-op once the directory exists, the same pattern `StateStore` already uses for `state/`.

ghstars never runs `git` against `config/`, the same as `state/`. If the user tracks `config/` in git, that is their own dotfiles-repo workflow above, not an action ghstars takes.

## Amendment (ticket 30)

The `GHSTARS_HOME` environment variable overrides the fixed `~/.ghstars/`
tree. `ghstars.cli.deps.get_ghstars_home()` reads it and falls back to
`DEFAULT_GHSTARS_HOME` (`~/.ghstars/`) when it is unset; every path getter
in that module calls it, so an override relocates `state/` and `config/`
together. This exists so a live test, or an agent, can point at an
isolated directory instead of the user's real account state, without
touching the single-directory layout this ADR decided: the override
still puts `config/` and `state/` under one tree, just a different one.
