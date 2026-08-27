import sys
from pathlib import Path

from ghstars.core.github_client import GitHubClient
from ghstars.core.state_store import StateStore
from ghstars.github import RealGitHubClient

# Three-tier config (ticket 32): `config/` holds one file per layer, and
# a setting lives in exactly one of them, never two.
#
# - Core concerns (settings every layer above `ghstars.core` shares) live
#   in `ghstars.toml` -- `get_core_config_path()`, loaded by
#   `ghstars.core.config.load_core_config`.
# - CLI-only concerns live in `cli.toml` -- `get_cli_config_path()`. No
#   loader reads it yet; ticket 30 adds the first CLI-tier setting.
# - TUI-only concerns live in `tui.toml` -- `get_tui_config_path()`,
#   loaded by `ghstars.tui.config.load_tui_config`. ADR 0008's own
#   config/state rule still governs what belongs in `tui.toml` versus
#   `state/tui-state.toml`; ticket 32 doesn't touch that split.
#
# The test for a new setting: would every consumer of `ghstars.core` want
# it? Core. Would only the CLI ever read it? CLI. Would only the TUI ever
# read it? TUI. Never put the same fact in two of these files.
GHSTARS_HOME = Path.home() / ".ghstars"


def get_client() -> GitHubClient:
    return RealGitHubClient()


def get_store() -> StateStore:
    return StateStore(GHSTARS_HOME / "state")


def ensure_config_dir() -> Path:
    """Scaffold `~/.ghstars/config/` if it's missing.

    No default file content — every tier's schema is defined in code
    (`ghstars.core.config` for `ghstars.toml`, `ghstars.tui.config` for
    `tui.toml`; `cli.toml` has no loader yet), but nothing scaffolds a
    file with default content; taxonomy definitions (ticket 07) are
    still undefined. Just the empty directory, mirroring how StateStore
    already auto-creates state/ on construction.
    """
    path = GHSTARS_HOME / "config"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_core_config_path() -> Path:
    """`~/.ghstars/config/ghstars.toml` (ticket 32).

    Not scaffolded with default content — same reasoning as
    `ensure_config_dir()` for `config/` itself: a missing file means
    "every core default applies" (`ghstars.core.config.load_core_config`
    treats it as empty config), and ghstars never writes into `config/`
    on the user's behalf (ADR 0002).

    Holds every core-tier setting under its own table, e.g. `[export]`
    for the ticket 10 export engine, folded in here by ticket 32 — see
    `check_stale_export_config()` for the retired standalone
    `export.toml`.
    """
    return GHSTARS_HOME / "config" / "ghstars.toml"


def get_cli_config_path() -> Path:
    """`~/.ghstars/config/cli.toml` (ticket 32).

    Not scaffolded with default content, same reasoning as
    `get_core_config_path()`. No loader reads this file yet — ticket 30
    adds the first CLI-tier setting (a configurable default row cap);
    this getter exists ahead of it so the three-tier layout is in place
    before that setting needs a home.
    """
    return GHSTARS_HOME / "config" / "cli.toml"


def check_stale_export_config() -> None:
    """Warn once on stderr if a leftover `config/export.toml` exists.

    Ticket 32 folds export config into the `[export]` table of
    `ghstars.toml` and deletes the `export.toml` load path outright —
    no migration, no back-compat read, because nothing has released yet.
    A file ghstars no longer reads must not silently change behavior,
    but it also must not vanish without a trace — the same "never guess,
    always surface" principle a bad config file already gets via
    `CoreConfigError`. So ghstars warns once per invocation, on stderr,
    rather than pretending the file isn't there.
    """
    stale = GHSTARS_HOME / "config" / "export.toml"
    if stale.exists():
        print(
            f"warning: {stale} is no longer read. Export config now "
            f"lives in the [export] table of {get_core_config_path()} "
            "(ticket 32) — move your entries there and delete this "
            "file.",
            file=sys.stderr,
        )


def get_tui_config_path() -> Path:
    """`~/.ghstars/config/tui.toml` (ticket 21).

    Not scaffolded with default content, same reasoning as
    `get_core_config_path()`: a missing file means "every TUI
    default applies" (`ghstars.tui.config.load_tui_config`), and
    ghstars never writes into `config/` on the user's behalf (ADR
    0002) — `tui.toml` stays stow-managed dotfiles, hand-edited by
    the user.
    """
    return GHSTARS_HOME / "config" / "tui.toml"


def get_tui_state_path() -> Path:
    """`~/.ghstars/state/tui-state.toml` (ticket 21).

    Lives under `state/`, alongside `StateStore`'s own `stars.json`/
    `lists.json` — machine-owned, read at TUI launch and written back
    at quit (spec story 71). A missing file means every default
    applies, same rule as `get_tui_config_path()`.
    """
    return GHSTARS_HOME / "state" / "tui-state.toml"
