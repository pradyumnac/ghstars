import json
from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import BaseModel, ValidationError

from ghstars.core.github_client import GitHubClient
from ghstars.core.models import List, RetriageEntry, Star
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


def sync(
    client: GitHubClient,
    store: StateStore,
    *,
    on_stage: Callable[[str], None] | None = None,
) -> SyncResult:
    """`on_stage`, if given, is called with a short human-readable label
    before each major phase below -- the caller's seam for surfacing
    progress on a run that is normally silent until it finishes (e.g.
    `sync_cmd`'s spinner). Purely a progress hook: `sync()`'s own
    behavior and return value never depend on whether it is set.
    """
    report = on_stage or (lambda _stage: None)

    report("Checking rate limit")
    status = client.check_rate_limit()
    if not status.ok:
        raise RateLimitExceededError(
            f"rate limit exceeded: {status.remaining}/{status.limit} remaining"
        )

    # Hold the lock across the full read-diff-write span.
    with store.lock():
        previous = _load_previous_stars(store)
        report("Fetching starred repos")
        stars = client.fetch_stars()
        archived = _carry_forward_archived(previous, stars, now=datetime.now(UTC))
        all_stars = stars + archived

        # Classify Lists before saving either local snapshot.
        report("Fetching Lists")
        lists = [classify_list(lst) for lst in client.fetch_lists()]
        all_stars = reconcile_list_membership(all_stars, lists)

        # Merge pending edits against the fresh GitHub state.
        report("Pushing pending tag changes")
        now = datetime.now(UTC)
        all_stars, lists, failed_tag_pushes, conflicts = _merge_pending_list_membership(
            client, previous=previous, current=all_stars, lists=lists, now=now
        )

        # Save conflicts before snapshots so failed writes remain recoverable.
        report("Saving local state")
        if conflicts:
            store.save_retriage([*_load_previous_retriage(store), *conflicts])
        store.save_stars(all_stars)
        store.save_lists(lists)
    return SyncResult(
        star_count=len(all_stars),
        list_count=len(lists),
        failed_tag_pushes=failed_tag_pushes,
    )


def _load_self_healing[T](loader: Callable[[], list[T]]) -> list[T]:
    """Run a `StateStore` loader, treating a corrupt/missing/unparseable
    local file as "nothing saved yet," not a fatal error -- shared by
    every local-only snapshot `sync()` reads before writing a fresh one
    (`stars.json` for the archived-diff, `retriage.json` for the
    Retriage Queue). `sync()` must stay recoverable even when one of its
    own local files is corrupt.
    """
    try:
        return loader()
    except OSError, json.JSONDecodeError, ValidationError:
        return []


def _load_previous_stars(store: StateStore) -> list[Star]:
    """Load the prior snapshot for the archived-diff. Self-heals on read."""
    return _load_self_healing(store.load_stars)


def _load_previous_retriage(store: StateStore) -> list[RetriageEntry]:
    """Load the existing Retriage Queue so a new conflict is appended,
    never overwrites it. Self-heals on read, same reasoning as
    `_load_previous_stars`: a corrupt `retriage.json` must not block a
    sync, just lose whatever queue history it held.
    """
    return _load_self_healing(store.load_retriage)


def _merge_pending_list_membership(
    client: GitHubClient,
    *,
    previous: list[Star],
    current: list[Star],
    lists: list[List],
    now: datetime,
) -> tuple[list[Star], list[List], list[str], list[RetriageEntry]]:
    """Merge each Star's staged List-membership edit against GitHub, as
    a three-way merge, once per sync (ticket 05).

    Run this after `fetch_stars()`, `fetch_lists()`, and
    `reconcile_list_membership()`. "Remote" is then this sync's fresh
    state, not a stale guess.

    The three sides:

    - base: `list_ids` on `previous`, from before this sync's fetch.
    - remote: `list_ids` on `current`, which `reconcile_list_membership`
      just set from this sync's pull.
    - local: `pending_list_ids` on `previous`. This is always the full
      desired set, never a delta, the same convention `tag_star()`
      writes.

    The four outcomes:

    - No pending edit, or local equals base: push nothing. Remote
      stands.
    - Local changed and remote did not: push local.
    - Both changed to the same result: push nothing.
    - Both changed to different results: GitHub wins. Record the local
      edit in the Retriage Queue (ADR 0001). Never push it, never apply
      it, and never merge the two sets.

    Skip an Archived star. `archive_star()` already cleared its
    `pending_list_ids`, so a staged edit for a repo unstarred since it
    was tagged is moot.

    Isolate a failed push. One star's failure never aborts the others.
    A failure is never retried next sync, because `fetch_stars()`
    always returns fresh Stars with `pending_list_ids=None`.

    Catch `Exception` broadly on purpose. `ghstars.core` depends only on
    the `GitHubClient` Protocol, never on a concrete implementation's
    error types.
    """
    base_by_name = {star.full_name: star.list_ids for star in previous}
    pending_by_name = {
        star.full_name: star.pending_list_ids
        for star in previous
        if star.pending_list_ids is not None
    }

    failed: list[str] = []
    conflicts: list[RetriageEntry] = []
    updated_stars: list[Star] = []
    updated_lists = lists

    for star in current:
        local = pending_by_name.get(star.full_name)
        if local is None or star.archived:
            updated_stars.append(star)
            continue

        base_set = set(base_by_name.get(star.full_name, []))
        remote_set = set(star.list_ids)
        local_set = set(local)

        if local_set == base_set:
            # No real local edit to push; remote stands as-is.
            updated_stars.append(star)
            continue

        if remote_set == base_set:
            # Only local changed — push it.
            try:
                client.update_list_membership_for_item(star.full_name, local)
            except Exception:  # noqa: BLE001 -- broad on purpose, see docstring
                failed.append(star.full_name)
                updated_stars.append(star)
                continue
            updated_lists = apply_membership_diff(
                updated_lists, star.full_name, old_ids=star.list_ids, new_ids=local
            )
            updated_stars.append(star.model_copy(update={"list_ids": local}))
        elif local_set == remote_set:
            # Both landed on the same result already — no-op.
            updated_stars.append(star)
        else:
            # GitHub wins; retain the local edit in the Retriage Queue.
            conflicts.append(
                RetriageEntry(
                    star_full_name=star.full_name,
                    attempted_list_ids=local,
                    conflict_detected_at=now,
                )
            )
            updated_stars.append(star)

    return updated_stars, updated_lists, failed, conflicts


def apply_membership_diff(
    lists: list[List], full_name: str, *, old_ids: list[str], new_ids: list[str]
) -> list[List]:
    """Mirror a successful List-membership push's effect onto the
    already-fetched `lists`' `items`, so a saved Lists snapshot agrees
    with a saved Stars snapshot without a second `fetch_lists()` round
    trip. Mirrors what `client.update_list_membership_for_item` itself
    just did remotely (see e.g.
    `FakeGitHubClient.update_list_membership_for_item`).

    Shared by this module's own `_merge_pending_list_membership` (ticket
    05) and `ghstars.core.category.drain_category` (ticket 07) -- the
    same "which Lists gained/lost this item" diff either way, whether the
    push came from a sync-time three-way merge or a bulk Category drain.
    Extracted here (ticket 19) rather than kept as two near-identical
    private copies; `category.py` already depends on this module
    (`reconcile_list_membership`), so importing this one adds no new
    cycle.
    """
    removed = set(old_ids) - set(new_ids)
    added = set(new_ids) - set(old_ids)
    if not removed and not added:
        return lists

    result: list[List] = []
    for lst in lists:
        if lst.id in removed and full_name in lst.items:
            result.append(
                lst.model_copy(
                    update={"items": [i for i in lst.items if i != full_name]}
                )
            )
        elif lst.id in added and full_name not in lst.items:
            result.append(lst.model_copy(update={"items": [*lst.items, full_name]}))
        else:
            result.append(lst)
    return result


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
