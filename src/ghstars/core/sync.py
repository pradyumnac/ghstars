from pydantic import BaseModel

from ghstars.core.github_client import GitHubClient
from ghstars.core.state_store import StateStore
from ghstars.core.taxonomy import classify_list


class RateLimitExceededError(Exception):
    """Raised when a sync would exceed the GitHub API rate limit.

    Checked before any fetch begins so a large sync never gets stuck
    mid-way with half-updated local state (spec story 13).
    """


class SyncResult(BaseModel):
    star_count: int
    list_count: int


def sync(client: GitHubClient, store: StateStore) -> SyncResult:
    status = client.check_rate_limit()
    if not status.ok:
        raise RateLimitExceededError(
            f"rate limit exceeded: {status.remaining}/{status.limit} remaining"
        )

    stars = client.fetch_stars()

    # Lists (ticket 03): fetched Lists carry only their raw `name` from
    # GitHub -- classify_list() derives intent/category/malformed from it
    # before persisting, so GitHub-side classification is always respected.
    # Fetched before either save below, so a failure here never leaves
    # stars.json updated while lists.json is stale (or vice versa).
    lists = [classify_list(lst) for lst in client.fetch_lists()]

    store.save_stars(stars)
    store.save_lists(lists)

    return SyncResult(star_count=len(stars), list_count=len(lists))
