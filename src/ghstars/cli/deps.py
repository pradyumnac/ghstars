from pathlib import Path

from ghstars.core.github_client import GitHubClient
from ghstars.core.state_store import StateStore
from ghstars.github import RealGitHubClient


def get_client() -> GitHubClient:
    return RealGitHubClient()


def get_store() -> StateStore:
    return StateStore(Path.home() / ".ghstars" / "state")
