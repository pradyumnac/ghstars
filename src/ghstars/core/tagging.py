from pydantic import BaseModel

from ghstars.core.github_client import GitHubClient
from ghstars.core.models import Star
from ghstars.core.state_store import StateStore
from ghstars.core.taxonomy import classify_list, strip_lifecycle_siblings


class StarNotFoundError(Exception):
    """`ghstars tag` targeted a repo with no local Star record."""


class StarArchivedError(Exception):
    """`ghstars tag` targeted a repo that's Archived (unstarred) locally.

    Not a valid tagging target — CONTEXT.md is explicit that Archived
    carries no List membership going forward.
    """


class TagResult(BaseModel):
    """The result of `tag_star()`.

    Holds the updated Star, plus the ids of any sibling Lists it was
    auto-removed from. This keeps Explore, Current, and Retired
    mutually exclusive per Category (spec story 16).

    This reports removed Lists by id, not by name. A name lookup would
    need an id-to-name table that `tag_star()` does not otherwise need.
    Report by id and count only, until a caller actually needs names.
    """

    star: Star
    removed_list_ids: list[str] = []


def tag_star(
    client: GitHubClient,
    store: StateStore,
    full_name: str,
    list_name: str,
    *,
    is_private: bool = False,
) -> TagResult:
    """Stage `full_name` for addition to `list_name`, locally.

    Creates the List for real immediately if it does not exist yet.
    Checks live GitHub state for that (`client.fetch_lists()`), not the
    local cache — a stale cache could otherwise create a duplicate List
    GitHub already has under the same name. Stages the Star<->List
    membership as `pending_list_ids` only; the actual push happens at
    the next sync, so ticket 05's three-way merge can arbitrate any
    conflict there.

    Suppose the target List's intent is Explore, Current, or Retired.
    Then this strips any sibling List first: same Category, a
    *different* one of those three intents. This is spec story 16.
    This is an auto-resolve, not a hard error. So moving a Star from
    Current to Retired (story 17) is one `tag` call. The user does not
    need to untag first.

    This always reads the freshest local Star state and the freshest
    fetched Lists. So a second `tag` call into a sibling intent, before
    the next sync, still sees the first call's staged edit. It strips
    that edit correctly too. By the time
    `_merge_pending_list_membership` (ticket 05) sees a pending edit,
    the edit is already exclusivity-clean. `sync.py` needs no change
    for this.
    """
    with store.lock():
        stars = store.load_stars()
        star = next((s for s in stars if s.full_name == full_name), None)
        if star is None:
            raise StarNotFoundError(full_name)
        if star.archived:
            raise StarArchivedError(full_name)

        lists = [classify_list(lst) for lst in client.fetch_lists()]
        lst = next((item for item in lists if item.name == list_name), None)
        if lst is None:
            lst = classify_list(client.create_list(list_name, is_private=is_private))
            lists = [*lists, lst]
        store.save_lists(lists)

        current = (
            star.pending_list_ids
            if star.pending_list_ids is not None
            else star.list_ids
        )

        current, removed_list_ids = strip_lifecycle_siblings(
            current, lists=lists, target=lst
        )

        new_ids = current if lst.id in current else [*current, lst.id]
        updated = star.model_copy(update={"pending_list_ids": new_ids})
        store.save_stars([updated if s.full_name == full_name else s for s in stars])
    return TagResult(star=updated, removed_list_ids=removed_list_ids)
