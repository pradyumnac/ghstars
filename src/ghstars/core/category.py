"""Category rename & drain (ticket 07).

`ghstars category rename` renames a Category across its Explore/Current/
Retired List variants in one operation, instead of the user manually
renaming each one by hand. `ghstars category drain` bulk-migrates every
Star from one Category into another, matching each Star's existing
lifecycle Intent -- Explore stays Explore, Current stays Current,
Retired stays Retired. Neither command ever crosses Intents; that stays
`ghstars tag`'s job, one Star at a time.

Both commands are scoped to CONTEXT.md's Category vocabulary
specifically -- Explore/Current/Retired Lists only. Reference Lists use
"Topic" for their after-colon label (CONTEXT.md), a different concept;
General Lists (`intent=None`) have no Category at all. Neither command
touches either.

Design constraint, added to ticket 07's own acceptance criteria during
ticket 17's review: both commands fetch fresh GitHub state right before
computing/writing the bulk change, and skip-and-report -- never
silently overwrite -- any List or Star whose live state has already
diverged from the local snapshot that triggered the operation (e.g. a
concurrent edit made on github.com or the phone app since the last
`ghstars sync`). This is a lighter fetch-then-skip-diverged rule than
ticket 05's three-way merge: neither command has a user-staged local
pending edit to preserve, just a computed migration/rename intent, so a
diverged target is simply skipped, not routed to the Retriage Queue
(ticket 17's design rationale).
"""

from pydantic import BaseModel

from ghstars.core.github_client import GitHubClient
from ghstars.core.models import List
from ghstars.core.state_store import StateStore
from ghstars.core.sync import apply_membership_diff, reconcile_list_membership
from ghstars.core.taxonomy import (
    LIFECYCLE_INTENTS,
    classify_list,
    strip_lifecycle_siblings,
)


class InvalidCategoryNameError(Exception):
    """`rename`/`drain` was given a blank Category name."""


class CategoryNotFoundError(Exception):
    """`rename`/`drain` targeted a Category with no Explore/Current/
    Retired List, per the local snapshot from the last `ghstars sync`.

    Raised before any GitHub call is made -- there is nothing to fetch
    fresh state for if the local snapshot names nothing to act on.
    """


class RenameResult(BaseModel):
    """The result of `rename_category()`.

    Reports by List id, not name, matching `TagResult`'s convention
    (`ghstars.core.tagging`) -- id and count only, until a caller
    actually needs names.
    """

    renamed: list[str] = []
    skipped: list[str] = []


class DrainResult(BaseModel):
    """The result of `drain_category()`. Reports Star `full_name`s."""

    migrated: list[str] = []
    skipped: list[str] = []


def rename_category(
    client: GitHubClient, store: StateStore, old: str, new: str
) -> RenameResult:
    """Rename Category `old` to `new` across its Explore/Current/Retired
    List variants, consistently, in one operation.

    Uses `store.load_lists()` -- the local snapshot from the last sync
    -- to decide *which* Lists this rename targets (the "trigger").
    Then fetches fresh GitHub state (`client.fetch_lists()`) right
    before writing, and skips (reports, never overwrites) any target
    whose live name/Category/Intent has already diverged from that
    local snapshot -- e.g. someone renamed or reclassified the same
    List on github.com since the last `ghstars sync` (see module
    docstring). Also skips a target when the destination name is
    already taken by a *different* live List, rather than creating a
    same-name duplicate.

    A renamed List's new name is always `f"{intent}: {new}"`, built
    from the fixed Intent prefix plus `new` verbatim -- this can never
    produce a malformed name (`ghstars.core.taxonomy.parse_list_name`
    always matches the exact prefix first), satisfying ticket 07's
    "no malformed names produced" acceptance criterion structurally,
    not via a separate validation step.
    """
    old = old.strip()
    new = new.strip()
    if not old or not new:
        raise InvalidCategoryNameError("category name cannot be blank")

    with store.lock():
        # Re-classify local Lists before selecting targets.
        local_lists = [classify_list(lst) for lst in store.load_lists()]
        targets = {
            lst.id: lst
            for lst in local_lists
            if lst.intent in LIFECYCLE_INTENTS and lst.category == old
        }
        if not targets:
            raise CategoryNotFoundError(old)

        if old == new:
            return RenameResult(renamed=[], skipped=[])

        fresh_lists = _fetch_fresh_lists(client)
        fresh_by_id = {lst.id: lst for lst in fresh_lists}

        renamed: list[str] = []
        skipped: list[str] = []
        result_lists = fresh_lists

        for list_id, local_lst in targets.items():
            fresh_lst = _undiverged(local_lst, fresh_by_id)
            if fresh_lst is None:
                # Skip Lists that changed since the local snapshot.
                skipped.append(list_id)
                continue

            new_name = f"{fresh_lst.intent}: {new}"
            name_taken = any(
                lst.id != list_id and lst.name == new_name for lst in fresh_lists
            )
            if name_taken:
                skipped.append(list_id)
                continue

            try:
                updated = client.update_list(list_id, name=new_name)
            except Exception:  # noqa: BLE001 -- Protocol-only errors, see sync.py's precedent
                skipped.append(list_id)
                continue
            classified = classify_list(updated)
            result_lists = [
                classified if lst.id == list_id else lst for lst in result_lists
            ]
            renamed.append(list_id)

        store.save_lists(result_lists)
    return RenameResult(renamed=renamed, skipped=skipped)


def drain_category(
    client: GitHubClient,
    store: StateStore,
    from_category: str,
    to_category: str,
    *,
    is_private: bool = False,
) -> DrainResult:
    """Bulk-migrate every Star from Category `from_category` into
    Category `to_category`, one lifecycle Intent at a time -- a Star
    currently in `Explore: {from_category}` lands in
    `Explore: {to_category}`, `Current` stays `Current`, `Retired`
    stays `Retired`.

    Uses `store.load_lists()` -- the local snapshot from the last sync
    -- to decide which Stars this drain targets (the "trigger"). Then
    fetches fresh GitHub state (`client.fetch_lists()`,
    `client.fetch_stars()`) right before computing/writing the bulk
    change, and skips (reports, never overwrites) any Star whose live
    List membership has already diverged from that local snapshot --
    e.g. someone already moved it, untagged it, or unstarred it on
    github.com since the last `ghstars sync` (ticket 07's fresh-state-
    check acceptance criterion, added during ticket 17's review; see
    module docstring).

    A destination List missing for a given Intent is created lazily, at
    most once per Intent, public by default unless `is_private` (spec
    story 48, matching `ghstars.core.tagging.tag_star`'s convention).

    Migrating a Star can surface the same mutual-exclusivity conflict
    `tag_star` resolves (ticket 17, spec story 16): the Star might
    already sit in a *different* lifecycle List under `to_category`
    (e.g. draining `Explore: from` into `Explore: to`, while the Star
    already sits in `Current: to` for unrelated reasons). Reuses
    `ghstars.core.taxonomy.strip_lifecycle_siblings` -- the same
    invariant, not a re-derived copy.
    """
    from_category = from_category.strip()
    to_category = to_category.strip()
    if not from_category or not to_category:
        raise InvalidCategoryNameError("category name cannot be blank")

    with store.lock():
        # Re-classify local Lists before selecting targets.
        local_lists = [classify_list(lst) for lst in store.load_lists()]
        from_targets = [
            lst
            for lst in local_lists
            if lst.intent in LIFECYCLE_INTENTS and lst.category == from_category
        ]
        if not from_targets:
            raise CategoryNotFoundError(from_category)

        if from_category == to_category:
            return DrainResult(migrated=[], skipped=[])

        fresh_lists = _fetch_fresh_lists(client)
        fresh_stars = reconcile_list_membership(client.fetch_stars(), fresh_lists)

        fresh_lists_by_id = {lst.id: lst for lst in fresh_lists}
        # Patch the local snapshot; do not overwrite staged or archived fields.
        fresh_stars_by_name = {star.full_name: star for star in fresh_stars}
        local_stars_by_name = {star.full_name: star for star in store.load_stars()}

        migrated: list[str] = []
        skipped: list[str] = []
        result_lists = fresh_lists

        for local_from in from_targets:
            intent = local_from.intent
            fresh_from = _undiverged(local_from, fresh_lists_by_id)
            if fresh_from is None:
                # Skip a source List that changed since the local snapshot.
                skipped.extend(local_from.items)
                continue

            live_members = set(fresh_from.items)
            eligible: list[str] = []
            for full_name in local_from.items:
                star = fresh_stars_by_name.get(full_name)
                if full_name not in live_members or star is None or star.archived:
                    # Skip stars whose live membership no longer matches.
                    skipped.append(full_name)
                    continue
                eligible.append(full_name)

            if not eligible:
                continue

            to_list = next(
                (
                    lst
                    for lst in result_lists
                    if lst.intent == intent and lst.category == to_category
                ),
                None,
            )
            if to_list is None:
                try:
                    created = client.create_list(
                        f"{intent}: {to_category}", is_private=is_private
                    )
                except Exception:  # noqa: BLE001 -- Protocol-only errors, see sync.py's precedent
                    skipped.extend(eligible)
                    continue
                to_list = classify_list(created)
                result_lists = [*result_lists, to_list]

            for full_name in eligible:
                star = fresh_stars_by_name[full_name]
                without_source = [i for i in star.list_ids if i != fresh_from.id]
                if to_list.id in without_source:
                    desired = without_source
                else:
                    stripped, _removed = strip_lifecycle_siblings(
                        without_source, lists=result_lists, target=to_list
                    )
                    desired = [*stripped, to_list.id]

                try:
                    client.update_list_membership_for_item(full_name, desired)
                except Exception:  # noqa: BLE001 -- Protocol-only errors, see sync.py's precedent
                    skipped.append(full_name)
                    continue

                result_lists = apply_membership_diff(
                    result_lists, full_name, old_ids=star.list_ids, new_ids=desired
                )
                # Update only membership and preserve the remaining local fields.
                local_record = local_stars_by_name.get(full_name)
                if local_record is not None:
                    local_stars_by_name[full_name] = local_record.model_copy(
                        update={"list_ids": desired}
                    )
                migrated.append(full_name)

        store.save_stars(list(local_stars_by_name.values()))
        store.save_lists(result_lists)
    return DrainResult(migrated=migrated, skipped=skipped)


def _fetch_fresh_lists(client: GitHubClient) -> list[List]:
    """Fetch and classify GitHub's current List state, right before
    writing a bulk rename/drain (see module docstring's fetch-fresh-
    skip-diverged design constraint).

    Shared by `rename_category()` and `drain_category()` (ticket 19) --
    the fetch half of the "fetch fresh, skip diverged" primitive; pair
    with `_undiverged()` below.
    """
    return [classify_list(lst) for lst in client.fetch_lists()]


def _undiverged(local: List, fresh_by_id: dict[str, List]) -> List | None:
    """The fresh List matching `local.id`, or `None` if it has diverged
    from the local snapshot that named `local` a rename/drain target --
    deleted, renamed, or reclassified into a different Intent/Category on
    GitHub since the last `ghstars sync`.

    Shared by `rename_category()` and `drain_category()` (ticket 19),
    extracted from what were two independent, identically-shaped
    divergence checks -- the diff half of the "fetch fresh, skip
    diverged" primitive; pair with `_fetch_fresh_lists()` above. Both
    callers skip (report, never overwrite) a diverged target rather than
    act against a moving target (module docstring).
    """
    fresh = fresh_by_id.get(local.id)
    if (
        fresh is None
        or fresh.intent != local.intent
        or fresh.category != local.category
    ):
        return None
    return fresh
