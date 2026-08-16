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

    No default file content yet — no ticket has defined config/'s
    schema (taxonomy definitions land with ticket 07, export mappings
    with ticket 10). Just the empty directory, mirroring how
    StateStore already auto-creates state/ on construction.
    """
    path = GHSTARS_HOME / "config"
    path.mkdir(parents=True, exist_ok=True)
    return path
