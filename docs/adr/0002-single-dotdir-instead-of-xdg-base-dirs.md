# Single ~/.ghstars/ directory instead of XDG base dirs

Most modern CLI tools split config/data/state across `$XDG_CONFIG_HOME`, `$XDG_DATA_HOME`, and `$XDG_STATE_HOME`. ghstars deliberately doesn't: everything lives under one `~/.ghstars/` tree (`config/`, `state/`, `runtime/`).

The user manages dotfiles with GNU Stow and keeps config in plain-text, git-diffable formats specifically so they can be symlinked into a dotfiles repo. A single directory is trivial to stow; three directories scattered across the XDG hierarchy are not. `config/` and `state/` use TOML/YAML for this reason — `runtime/` (caches, nudge files) is the one subtree that's fine to stay untracked.

`ensure_config_dir()` in `cli/deps.py` creates `~/.ghstars/config/` on every CLI run, before any command runs. The directory starts empty — no ticket has defined its file content yet. The create step is a no-op once the directory exists, the same pattern `StateStore` already uses for `state/`.

ghstars never runs `git` against `config/`, the same as `state/`. If the user tracks `config/` in git, that is their own dotfiles-repo workflow above, not an action ghstars takes.
