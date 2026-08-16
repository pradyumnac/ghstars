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
    failed_tag_pushes: list[str] = []


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
        failed_tag_pushes = _push_pending_list_membership(client, previous)
        stars = client.fetch_stars()
        archived = _carry_forward_archived(previous, stars, now=datetime.now(UTC))
        all_stars = stars + archived

        # Fetched Lists carry only raw `name` from GitHub (spec story 2);
        # classify_list() derives intent/category/malformed before persisting.
        # Fetched before either save below, so a failure here never leaves
        # stars.json updated while lists.json is stale, or vice versa.
        lists = [classify_list(lst) for lst in client.fetch_lists()]
        all_stars = reconcile_list_membership(all_stars, lists)

        store.save_stars(all_stars)
        store.save_lists(lists)
    return SyncResult(
        star_count=len(all_stars),
        list_count=len(lists),
        failed_tag_pushes=failed_tag_pushes,
    )


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


def _push_pending_list_membership(
    client: GitHubClient, previous: list[Star]
) -> list[str]:
    """Push any locally staged `ghstars tag` edit to GitHub for real.

    Runs before the fresh pull in `sync()`, so that pull's own
    `fetch_lists()` + `reconcile_list_membership()` naturally picks up
    the pushed state — no separate merge step needed here.
    `pending_list_ids` always holds the full desired set, never a delta,
    so retrying a failed/partial push on the next sync is a harmless
    no-op on GitHub's side (story 32).

    Each push is isolated: one star's failure (e.g. it was unstarred on
    GitHub since it was tagged, before this sync ever ran) must not
    abort every other pending push, and must not leave that one star
    stuck retrying forever — `stars = client.fetch_stars()` right after
    this always returns fresh Star objects with `pending_list_ids=None`
    (see FakeGitHubClient.fetch_stars/RealGitHubClient.fetch_stars), so
    a failed push is simply not retried, not silently spun forever.
    Returns the full_names that failed, so the caller can tell the user
    instead of the failure vanishing unreported.

    Catches `Exception` broadly, on purpose: `ghstars.core` depends only
    on the `GitHubClient` Protocol, never on a concrete implementation's
    error types (`ghstars.github.GitHubApiError` included) — that
    boundary is why this can't catch anything narrower.
    """
    failed: list[str] = []
    for star in previous:
        if star.pending_list_ids is None:
            continue
        try:
            client.update_list_membership_for_item(
                star.full_name, star.pending_list_ids
            )
        except Exception:  # noqa: BLE001 -- broad on purpose, see docstring
            failed.append(star.full_name)
    return failed


def archive_star(star: Star, *, now: datetime) -> Star:
    """Mark a single Star Archived.

    Archived is a Star property: the repo was unstarred on GitHub.
    Never an Intent; never the same axis as a List's Retired Intent
    (CONTEXT.md). An unstarred repo drops out of every List
    automatically, so clear `list_ids` too. Also clear `pending_list_ids`
    — a staged `ghstars tag` edit for a repo that is no longer starred is
    moot, and left set it would get pushed again on the next sync.

    Shared by `sync()`'s unstar diff and the `ghstars unstar` command,
    so both agree on what "archived" means.
    """
    return star.model_copy(
        update={
            "archived": True,
            "archived_at": now,
            "list_ids": [],
            "pending_list_ids": None,
        }
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


def reconcile_list_membership(stars: list[Star], lists: list[List]) -> list[Star]:
    """Set each Star's `list_ids` from the Lists that actually contain it.

    `List.items` is the source of truth (fetched fresh from GitHub);
    `Star.list_ids` starts empty on every fetch (see
    docs/explanation/known-limitations.md). The relation is many-to-many:
    one repo can sit in several Lists, and one List holds many repos.

    A List item with no matching Star is skipped, not an error — the two
    fetches are not one atomic snapshot, so this can legitimately happen
    (see docs/explanation/known-limitations.md). It self-heals next sync.

    An Archived star is left untouched. `archive_star()` already cleared
    its `list_ids`, and CONTEXT.md is explicit that Archived carries no
    List membership going forward — a stale or racy `List.items` entry
    for an already-archived star must not override that.
    """
    membership: dict[str, list[str]] = {}
    for lst in lists:
        for full_name in lst.items:
            membership.setdefault(full_name, []).append(lst.id)

    return [
        star
        if star.archived
        else star.model_copy(update={"list_ids": membership.get(star.full_name, [])})
        for star in stars
    ]


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
