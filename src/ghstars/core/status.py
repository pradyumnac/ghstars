from collections.abc import Iterable
from datetime import datetime

from pydantic import BaseModel

from ghstars.core.models import List, Star
from ghstars.core.state_store import StateStore
from ghstars.core.taxonomy import (
    LIFECYCLE_INTENTS,
    TRIAGE_CATEGORY,
    blessed_categories,
)


class StatusReport(BaseModel):
    """Single-record health summary for `ghstars status` (ticket 08).

    Built entirely from `StateStore.load_*()` -- no live `GitHubClient`
    call -- so an agent can call this before deciding whether a `sync`
    is even worth the round trip.
    """

    last_sync_at: datetime | None
    active_star_count: int
    archived_star_count: int
    list_count: int
    unclassified_count: int
    pending_edit_count: int
    retriage_queue_count: int
    verify_ok: bool
    verify_problems: list[str] = []


def verify_state(
    stars: list[Star],
    lists: list[List],
    *,
    categories: Iterable[str] | None = None,
) -> list[str]:
    """Deterministic, offline structural checks against local state.

    Mirrors the old `gh-stars.py`'s `verify()` -- a flat list of problem
    strings, empty when everything checks out. Each check here targets
    corruption that would silently break other commands (a dangling
    `Star.list_ids` reference would make `ghstars stars --fields list_ids`
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

    Three further checks come from ADR 0005. They report taxonomy drift,
    not corruption, and they never block a command -- ticket 03's rule is
    that ghstars flags a taxonomy problem for the user to resolve and
    never guesses the repair. `verify_ok` therefore now means "no
    corruption *and* no taxonomy drift", which is wider than it was:

    - A Category outside the blessed vocabulary. This is the only check
      that needs `categories`, and the only one `None` skips. It is
      *not* `List.malformed`, which means the name shape is wrong; an
      unblessed Category has two valid repairs (rename the List, or
      bless the word in `ghstars.toml`).
    - A Star in the triage inbox and a classified List at once. Always
      checked. `General` means the subject is undecided, so it
      contradicts a decided Category on the same Star.
    - A Star holding two different lifecycle Intents. Always checked. At
      most one of Explore/Current/Retired applies across all of a Star's
      Lists.

    A Star only reaches the last two checks once `sync` has re-classified
    `lists.json` under ADR 0005. Until then a bare-name List still holds
    `intent=None, category=None` from the older parser, and these checks
    cannot see it.

    Args:
        categories: the blessed Category vocabulary, normally
            `CoreConfig.taxonomy.categories`. `None` skips the
            vocabulary check only; the other two always run.
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

    if categories is not None:
        blessed = blessed_categories(categories)
        for lst in lists:
            if lst.category is not None and lst.category not in blessed:
                problems.append(
                    f"unblessed Category {lst.category!r} in List {lst.name!r}: "
                    f"rename the List, or add it to [taxonomy] in ghstars.toml"
                )

    by_id = {lst.id: lst for lst in lists}
    for star in stars:
        member_lists = [by_id[i] for i in star.list_ids if i in by_id]

        in_triage = [lst for lst in member_lists if lst.category == TRIAGE_CATEGORY]
        classified = [
            lst
            for lst in member_lists
            if lst.category is not None and lst.category != TRIAGE_CATEGORY
        ]
        if in_triage and classified:
            problems.append(
                f"{star.full_name}: in the triage inbox "
                f"{sorted(lst.name for lst in in_triage)} and the classified List "
                f"{sorted(lst.name for lst in classified)} at the same time"
            )

        lifecycle = {
            lst.intent for lst in member_lists if lst.intent in LIFECYCLE_INTENTS
        }
        if len(lifecycle) > 1:
            problems.append(
                f"{star.full_name}: holds two lifecycle Intents "
                f"{sorted(str(i) for i in lifecycle)}; at most one of "
                f"Explore/Current/Retired applies to a Star"
            )

    return problems


def build_status(
    store: StateStore, *, categories: Iterable[str] | None = None
) -> StatusReport:
    """Assemble the `status` report from local state only.

    "Last sync time": there is no dedicated sync-timestamp field or file
    in local state (`Star.last_checked` is per-star). Derived here as
    the max `last_checked` across all Stars -- `None` when there are no
    Stars yet, i.e. before the first `sync`.

    "Unclassified": Stars with no List membership at all and not
    Archived -- a derived, local-only view, never a real GitHub List
    (ADR 0007). ghstars never auto-tags a never-classified Star into
    `Explore: General` or anywhere else; that List is an ordinary List
    the user opts into like any other, so it plays no special role
    here.

    "Pending-edit count": Stars whose `pending_list_ids` is not `None`
    (ticket 30 Scope 5). Stays `0` while ADR 0004 keeps pending-tag
    staging dormant -- no code path sets `pending_list_ids` today, so
    this count is a forward-looking field, not dead weight.

    Retriage Queue count: unresolved entries only (`resolved=False`),
    matching what `ghstars retriage` itself is for -- open conflicts to
    revisit, not a lifetime history.
    """
    stars = store.load_stars()
    lists = store.load_lists()
    retriage = store.load_retriage()

    last_sync_at = max((star.last_checked for star in stars), default=None)

    active_star_count = sum(1 for star in stars if not star.archived)
    archived_star_count = sum(1 for star in stars if star.archived)

    unclassified_count = sum(
        1 for star in stars if not star.archived and not star.list_ids
    )

    pending_edit_count = sum(1 for star in stars if star.pending_list_ids is not None)

    retriage_queue_count = sum(1 for entry in retriage if not entry.resolved)

    problems = verify_state(stars, lists, categories=categories)

    return StatusReport(
        last_sync_at=last_sync_at,
        active_star_count=active_star_count,
        archived_star_count=archived_star_count,
        list_count=len(lists),
        unclassified_count=unclassified_count,
        pending_edit_count=pending_edit_count,
        retriage_queue_count=retriage_queue_count,
        verify_ok=not problems,
        verify_problems=problems,
    )


__all__ = ["StatusReport", "build_status", "verify_state"]
