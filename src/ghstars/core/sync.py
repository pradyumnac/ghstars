from pydantic import BaseModel

from ghstars.core.github_client import GitHubClient
from ghstars.core.state_store import StateStore


class RateLimitExceededError(Exception):
    """Raised when a sync would exceed the GitHub API rate limit.

    Checked before any fetch begins so a large sync never gets stuck
    mid-way with half-updated local state (spec story 13).
    """


class SyncResult(BaseModel):
    star_count: int


def sync(client: GitHubClient, store: StateStore) -> SyncResult:
    status = client.check_rate_limit()
    if not status.ok:
        raise RateLimitExceededError(
            f"rate limit exceeded: {status.remaining}/{status.limit} remaining"
        )

    stars = client.fetch_stars()
    store.save_stars(stars)
    return SyncResult(star_count=len(stars))
