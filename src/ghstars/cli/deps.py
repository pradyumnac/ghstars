from pathlib import Path

from ghstars.core.github_client import GitHubClient
from ghstars.core.state_store import StateStore
from ghstars.github import RealGitHubClient

GHSTARS_HOME = Path.home() / ".ghstars"


def get_client() -> GitHubClient:
    return RealGitHubClient()


def get_store() -> StateStore:
    return StateStore(GHSTARS_HOME / "state")


def ensure_config_dir() -> Path:
    """Scaffold `~/.ghstars/config/` if it's missing.

    No default file content — `export.toml`'s schema is defined
    (`ghstars.core.export`, ticket 10), but nothing scaffolds it with
    default content; taxonomy definitions (ticket 07) are still
    undefined. Just the empty directory, mirroring how StateStore
    already auto-creates state/ on construction.
    """
    path = GHSTARS_HOME / "config"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_export_config_path() -> Path:
    """`~/.ghstars/config/export.toml` (ticket 10).

    Not scaffolded with default content — same reasoning as
    `ensure_config_dir()` for `config/` itself: a missing file means
    "no export mappings configured yet," not an error
    (`ghstars.core.export.load_export_config` treats it as empty
    config), and ghstars never writes into `config/` on the user's
    behalf (ADR 0002).
    """
    return GHSTARS_HOME / "config" / "export.toml"
