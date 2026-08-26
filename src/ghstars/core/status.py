from datetime import datetime

from pydantic import BaseModel

from ghstars.core.models import List, Star
from ghstars.core.state_store import StateStore
from ghstars.core.sync import EXPLORE_GENERAL


class StatusReport(BaseModel):
    """Single-record health summary for `ghstars status` (ticket 08).

    Built entirely from `StateStore.load_*()` -- no live `GitHubClient`
    call -- so an agent can call this before deciding whether a `sync`
    is even worth the round trip.
    """

    last_sync_at: datetime | None
    retriage_queue_count: int
    unclassified_count: int
    verify_ok: bool
    verify_problems: list[str] = []


def verify_state(stars: list[Star], lists: list[List]) -> list[str]:
    """Deterministic, offline structural checks against local state.

    Mirrors the old `gh-stars.py`'s `verify()` -- a flat list of problem
    strings, empty when everything checks out. Each check here targets
    corruption that would silently break other commands (a dangling
    `Star.list_ids` reference would make `ghstars list --fields list_ids`
    point at nothing; a duplicate id/full_name means state was written
    from something other than a clean `sync()` pass):

    - No duplicate `Star.full_name` in `stars.json` (`load_stars()`'s
      list has no natural uniqueness enforcement of its own).
    - No duplicate `List.id` in `lists.json`, same reasoning.
    - No `Star.list_ids` entry naming a `List.id` that isn't in
      `lists.json` -- every List a Star claims membership in must
      actually exist locally.

    Deliberately does *not* flag a `List.items` entry with no matching
    Star, or a `List.malformed=True` entry: both are already-documented,
    self-healing, non-corrupt states (`reconcile_list_membership`'s and
    `List.malformed`'s own docstrings), not structural damage.
    """
    problems: list[str] = []

    full_names = [star.full_name for star in stars]
    seen_names: set[str] = set()
    for name in full_names:
        if name in seen_names:
            problems.append(f"duplicate Star.full_name in stars.json: {name}")
        seen_names.add(name)

    list_ids = [lst.id for lst in lists]
    seen_ids: set[str] = set()
    for list_id in list_ids:
        if list_id in seen_ids:
            problems.append(f"duplicate List.id in lists.json: {list_id}")
        seen_ids.add(list_id)

    known_list_ids = set(list_ids)
    for star in stars:
        for list_id in star.list_ids:
            if list_id not in known_list_ids:
                problems.append(
                    f"{star.full_name}: list_ids references unknown List id {list_id!r}"
                )

    return problems


def build_status(store: StateStore) -> StatusReport:
    """Assemble the `status` report from local state only.

    "Last sync time": there is no dedicated sync-timestamp field or file
    in local state (`Star.last_checked` is per-star). Derived here as
    the max `last_checked` across all Stars -- `None` when there are no
    Stars yet, i.e. before the first `sync`.

    "Unclassified": Stars whose `list_ids` includes the `Explore:
    General` List's id, resolved by name against `load_lists()` (ticket
    05's default-classification target, `ghstars.core.sync.EXPLORE_GENERAL`).
    Zero, not an error, when that List hasn't been created locally yet.

    Retriage Queue count: unresolved entries only (`resolved=False`),
    matching what `ghstars retriage` itself is for -- open conflicts to
    revisit, not a lifetime history.
    """
    stars = store.load_stars()
    lists = store.load_lists()
    retriage = store.load_retriage()

    last_sync_at = max((star.last_checked for star in stars), default=None)

    explore_general = next((lst for lst in lists if lst.name == EXPLORE_GENERAL), None)
    unclassified_count = (
        sum(1 for star in stars if explore_general.id in star.list_ids)
        if explore_general is not None
        else 0
    )

    retriage_queue_count = sum(1 for entry in retriage if not entry.resolved)

    problems = verify_state(stars, lists)

    return StatusReport(
        last_sync_at=last_sync_at,
        retriage_queue_count=retriage_queue_count,
        unclassified_count=unclassified_count,
        verify_ok=not problems,
        verify_problems=problems,
    )


__all__ = ["StatusReport", "build_status", "verify_state"]
