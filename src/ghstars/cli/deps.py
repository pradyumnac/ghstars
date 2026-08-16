from datetime import UTC, datetime
from pathlib import Path

from ghstars.core.fake_client import FakeGitHubClient
from ghstars.core.github_client import GitHubClient
from ghstars.core.models import Star
from ghstars.core.state_store import StateStore


def _seed_stars() -> list[Star]:
    now = datetime(2026, 8, 16, tzinfo=UTC)
    return [
        Star(
            full_name="pradyumnac/ghstars",
            html_url="https://github.com/pradyumnac/ghstars",
            description="Classify GitHub stars into Lists.",
            starred_at=now,
            first_seen=now,
            language="Python",
            stargazer_count=1,
            last_checked=now,
        ),
    ]


def get_client() -> GitHubClient:
    """The one seam ticket 02 replaces: swap this for the real `gh`-backed client."""
    return FakeGitHubClient(stars=_seed_stars())


def get_store() -> StateStore:
    return StateStore(Path.home() / ".ghstars" / "state")
