import json
from datetime import UTC, datetime

from pydantic import BaseModel, ValidationError

from ghstars.core.github_client import GitHubClient
from ghstars.core.models import List, Star
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

    # Held across the whole read-diff-write span. FileLock is reentrant
    # within a thread, so load_stars/save_stars's internal locking nests
    # safely. This stops a concurrent `ghstars unstar` from reading a
    # stale snapshot and clobbering this write, or vice versa (story 33).
    with store.lock():
        previous = _load_previous_stars(store)
        stars = client.fetch_stars()
        archived = _carry_forward_archived(previous, stars, now=datetime.now(UTC))
        all_stars = stars + archived

        # Fetched Lists carry only raw `name` from GitHub (spec story 2);
        # classify_list() derives intent/category/malformed before persisting.
        # Fetched before either save below, so a failure here never leaves
        # stars.json updated while lists.json is stale, or vice versa.
        lists = [classify_list(lst) for lst in client.fetch_lists()]

        store.save_stars(all_stars)
        store.save_lists(lists)
    return SyncResult(star_count=len(all_stars), list_count=len(lists))


def _load_previous_stars(store: StateStore) -> list[Star]:
    """Load the prior snapshot for the archived-diff. Self-heals on read.

    A previous snapshot that fails to parse counts as "no history to
    diff against," not a fatal error. `sync()` must stay recoverable
    even when `stars.json` is corrupt.
    """
    try:
        return store.load_stars()
    except OSError, json.JSONDecodeError, ValidationError:
        return []


def archive_star(star: Star, *, now: datetime) -> Star:
    """Mark a single Star Archived.

    Archived is a Star property: the repo was unstarred on GitHub.
    Never an Intent; never the same axis as a List's Retired Intent
    (CONTEXT.md). An unstarred repo drops out of every List
    automatically, so clear `list_ids` too.

    Shared by `sync()`'s unstar diff and the `ghstars unstar` command,
    so both agree on what "archived" means.
    """
    return star.model_copy(
        update={"archived": True, "archived_at": now, "list_ids": []}
    )


def _carry_forward_archived(
    previous: list[Star], current: list[Star], *, now: datetime
) -> list[Star]:
    """Diff a sync's previous snapshot against a fresh fetch.

    A Star in `previous` but missing from `current` was unstarred since
    the last sync (story 5). Carry it forward, newly marked Archived
    (story 6, never dropped). A Star already Archived stays unchanged,
    so repeated syncs do not bump `archived_at` again.
    """
    current_names = {star.full_name for star in current}
    carried: list[Star] = []
    for star in previous:
        if star.full_name in current_names:
            continue
        carried.append(star if star.archived else archive_star(star, now=now))
    return carried


def remove_star_from_lists(lists: list[List], full_name: str) -> list[List]:
    """Drop `full_name` from every List's `items`.

    Mirrors `FakeGitHubClient.remove_star`. Used by `ghstars unstar` so
    the local Lists cache stays fresh until the next sync.
    """
    return [
        lst.model_copy(update={"items": [i for i in lst.items if i != full_name]})
        if full_name in lst.items
        else lst
        for lst in lists
    ]
