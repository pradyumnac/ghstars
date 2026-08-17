from pydantic import BaseModel

from ghstars.core.github_client import GitHubClient
from ghstars.core.models import List, Star
from ghstars.core.state_store import StateStore
from ghstars.core.taxonomy import classify_list, strip_lifecycle_siblings

# Design note (ticket 19, scope 5): tag_star() re-fetches Lists live on
# every call, by design (see its own docstring below) -- correct, but
# costly for a bulk caller (e.g. the TUI's bulk-tag action, ticket 09)
# tagging N stars into the same List: N redundant fetch_lists() round
# trips against state that hasn't actually changed between them, except
# for whatever tag_star() itself just created.
#
# Fix: an optional `lists: list[List] | None = None` keyword parameter.
# Omitted (every existing single-call-site caller: `ghstars tag`, the
# TUI's single-item tag path), behavior is unchanged -- tag_star() fetches
# fresh from `client.fetch_lists()` itself, exactly as before. Supplied,
# tag_star() trusts it instead of fetching (still defensively
# `classify_list`-ing it, so a raw unclassified fetch works too), and
# always returns the resulting (possibly List-creation-updated) snapshot
# on `TagResult.lists`, so a bulk caller can thread it through a loop:
#
#     lists = None
#     for full_name in targets:
#         result = tag_star(client, store, full_name, list_name, lists=lists)
#         lists = result.lists
#
# The caller must seed that loop with a *fresh* `client.fetch_lists()`
# (or leave it `None` for the first call) -- never the stale local
# `store.load_lists()` cache tag_star()'s own docstring warns against.
# Threading the returned snapshot forward keeps the loop's own List
# creation race-free (a List call N creates is visible to call N+1 via
# the returned snapshot, not a second live fetch) while cutting a
# same-List bulk-tag of N stars from N `fetch_lists()` round trips down
# to at most one for the whole batch. The remaining risk -- a *different*
# process creating a same-named List mid-batch -- is the same eventual-
# consistency class ticket 07's fetch-fresh-skip-diverged design already
# accepts elsewhere, not a new one.
#
# Considered and rejected:
# - A cache keyed by client identity: implicit, invisible staleness risk
#   across unrelated call sites (a concurrent `ghstars tag` in another
#   process wouldn't invalidate it).
# - A separate bulk `tag_stars()` function: a bigger API surface change,
#   and the TUI's bulk-tag loop already isolates one star's failure from
#   the rest (see `tui/app.py`'s `_apply_tag` docstring) -- collapsing
#   that into one call would need to preserve that isolation some other
#   way.


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
    # The List snapshot tag_star() actually used, classified, including
    # any List it just created. Always populated, whether `lists` was
    # supplied by the caller or freshly fetched internally -- see the
    # design note above tag_star() (ticket 19, scope 5). A bulk caller
    # threads this back into its next call's `lists=` argument.
    lists: list[List] = []


def tag_star(
    client: GitHubClient,
    store: StateStore,
    full_name: str,
    list_name: str,
    *,
    is_private: bool = False,
    lists: list[List] | None = None,
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

    `lists`, if supplied, is trusted instead of a fresh
    `client.fetch_lists()` call -- see the design note above this
    function (ticket 19, scope 5: bulk-tagging N stars into the same
    List without N redundant live fetches). Every existing
    single-call-site caller omits it and gets the original
    fetch-every-time behavior, unchanged. Defensively re-classified
    (`classify_list`) either way, same reasoning as
    `ghstars.core.category`'s targets -- correct even if a caller passes
    a raw, unclassified fetch straight through.
    """
    with store.lock():
        stars = store.load_stars()
        star = next((s for s in stars if s.full_name == full_name), None)
        if star is None:
            raise StarNotFoundError(full_name)
        if star.archived:
            raise StarArchivedError(full_name)

        lists = [
            classify_list(lst)
            for lst in (lists if lists is not None else client.fetch_lists())
        ]
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
    return TagResult(star=updated, removed_list_ids=removed_list_ids, lists=lists)
