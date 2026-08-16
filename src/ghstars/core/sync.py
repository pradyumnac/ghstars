import json
from datetime import UTC, datetime

from pydantic import BaseModel, ValidationError

from ghstars.core.github_client import GitHubClient
from ghstars.core.models import Star
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

    # Held across the whole read-diff-write span (StateStore's FileLock is
    # reentrant within a thread, so load_stars/save_stars's own internal
    # locking nests harmlessly) so a concurrent `ghstars unstar` can't read
    # a stale snapshot and clobber this sync's write, or vice versa (spec
    # story 33).
    with store.lock():
        previous = _load_previous_stars(store)
        stars = client.fetch_stars()
        archived = _carry_forward_archived(previous, stars, now=datetime.now(UTC))

        all_stars = stars + archived
        store.save_stars(all_stars)
    return SyncResult(star_count=len(all_stars))


def _load_previous_stars(store: StateStore) -> list[Star]:
    """Load the prior snapshot for the archived-diff, self-healing on read.

    Before this ticket, `sync()` never read `stars.json` first — it just
    overwrote it, so a corrupt or unreadable file could never block a
    sync. Reading it now (to diff for unstars) must not take away that
    self-healing property: a previous snapshot that fails to parse is
    treated as "no history to diff against" rather than a fatal error that
    would newly make `ghstars sync` itself unrecoverable.
    """
    try:
        return store.load_stars()
    except OSError, json.JSONDecodeError, ValidationError:
        return []


def archive_star(star: Star, *, now: datetime) -> Star:
    """Mark a single Star Archived.

    Archived is a Star property recording that the repo itself was
    unstarred on GitHub — never an Intent, and never the same axis as a
    List's Retired Intent (see CONTEXT.md's Archived/Retired entries). A
    repo unstarred on GitHub also drops out of every GitHub List
    automatically, so `list_ids` is cleared here to match.

    Shared by `sync()`'s unstar-detection diff (below) and the `ghstars
    unstar` CLI command, so both call sites agree on what "archived" means.
    """
    return star.model_copy(
        update={"archived": True, "archived_at": now, "list_ids": []}
    )


def _carry_forward_archived(
    previous: list[Star], current: list[Star], *, now: datetime
) -> list[Star]:
    """Diff a sync's previous local snapshot against a fresh fetch.

    A Star present in `previous` but missing from `current` was unstarred
    on GitHub since the last sync (spec story 5). It is never dropped
    (story 6) — it is carried forward here, newly marked Archived. A Star
    that was already Archived from an earlier sync is carried forward
    unchanged, so repeated syncs don't keep bumping `archived_at`.

    Deliberately kept as its own small helper, separate from `sync()`'s
    main body, so this diff stays easy to reason about independently.
    """
    current_names = {star.full_name for star in current}
    carried: list[Star] = []
    for star in previous:
        if star.full_name in current_names:
            continue
        carried.append(star if star.archived else archive_star(star, now=now))
    return carried
