from ghstars.core.github_client import GitHubClient
from ghstars.core.models import Star
from ghstars.core.state_store import StateStore
from ghstars.core.taxonomy import classify_list


class StarNotFoundError(Exception):
    """`ghstars tag` targeted a repo with no local Star record."""


class StarArchivedError(Exception):
    """`ghstars tag` targeted a repo that's Archived (unstarred) locally.

    Not a valid tagging target — CONTEXT.md is explicit that Archived
    carries no List membership going forward.
    """


def tag_star(
    client: GitHubClient,
    store: StateStore,
    full_name: str,
    list_name: str,
    *,
    is_private: bool = False,
) -> Star:
    """Stage `full_name` for addition to `list_name`, locally.

    Creates the List for real immediately if it does not exist yet.
    Checks live GitHub state for that (`client.fetch_lists()`), not the
    local cache — a stale cache could otherwise create a duplicate List
    GitHub already has under the same name, with no `ghstars` command
    to clean it up (delete_list lands in ticket 07). Stages the
    Star<->List membership as `pending_list_ids` only; the actual push
    happens at the next sync, so ticket 05's three-way merge can
    arbitrate any conflict there.
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
        new_ids = current if lst.id in current else [*current, lst.id]
        updated = star.model_copy(update={"pending_list_ids": new_ids})
        store.save_stars([updated if s.full_name == full_name else s for s in stars])
    return updated
