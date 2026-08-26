from pydantic import BaseModel

from ghstars.core.github_client import GitHubClient
from ghstars.core.models import List, Star
from ghstars.core.state_store import StateStore
from ghstars.core.sync import apply_membership_diff
from ghstars.core.taxonomy import classify_list, strip_lifecycle_siblings

# An optional Lists snapshot avoids redundant live fetches during bulk tagging.


class StarNotFoundError(Exception):
    """`ghstars tag` targeted a repo with no local Star record."""


class StarArchivedError(Exception):
    """`ghstars tag` targeted a repo that's Archived (unstarred) locally.

    Not a valid tagging target — CONTEXT.md is explicit that Archived
    carries no List membership going forward.
    """


class StarListMembershipDriftError(Exception):
    """The star's local `list_ids` (base) disagree with GitHub's live
    List membership for it, fetched moments ago by this same call
    (ticket 16).

    Raised *before* computing or pushing any edit — no auto-rebase, no
    silent GitHub-wins resolution at tag-time (that stays `sync()`'s
    job, see ADR 0004). The user must `ghstars sync` first, then retry
    `ghstars tag`.
    """

    def __init__(self, full_name: str, diverged_list_names: list[str]) -> None:
        self.full_name = full_name
        self.diverged_list_names = diverged_list_names
        names = ", ".join(diverged_list_names) if diverged_list_names else "(unknown)"
        super().__init__(
            f"{full_name}: local state has drifted from GitHub for {names} "
            "— run `ghstars sync` first, then retry."
        )


class TagPushError(Exception):
    """The immediate push to GitHub failed (network/API error, or the
    target List was deleted concurrently) — not a conflict.

    No local state is written when this is raised (ticket 16): `tag_star`
    fails outright, mirroring `unstar_cmd`'s remote-first,
    write-only-on-success pattern. There is no fallback staging.
    """

    def __init__(self, full_name: str, cause: Exception) -> None:
        self.full_name = full_name
        super().__init__(
            f"{full_name}: failed to push List membership to GitHub: {cause}"
        )


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
    # Return the classified snapshot so bulk callers can reuse it.
    lists: list[List] = []


def tag_star(
    client: GitHubClient,
    store: StateStore,
    full_name: str,
    list_name: str,
    *,
    is_private: bool = False,
    lists: list[List] | None = None,
    node_id: str | None = None,
) -> TagResult:
    """Add `full_name` to `list_name` and push it to GitHub immediately
    (ticket 16 — see ADR 0004 for why the older staged-edit machinery
    stays in the codebase, unused, rather than being deleted).

    Creates the List for real immediately if it does not exist yet.
    Checks live GitHub state for that (`client.fetch_lists()`), not the
    local cache — a stale cache could otherwise create a duplicate List
    GitHub already has under the same name.

    Before computing the new membership set, compares the star's local
    `list_ids` (base) against its *remote* membership, derived from the
    same `fetch_lists()` result (`List.items`) — free, no extra API
    call. If they disagree, GitHub's List membership for this star has
    drifted since the last `ghstars sync` and this raises
    `StarListMembershipDriftError` naming the diverged List(s); nothing
    is computed or pushed, nothing is staged. The user must `ghstars
    sync` first, then retry. When they agree, "base" and "remote" are
    the same set, so the new desired membership is computed from it
    directly — there is no separate "which side wins" question left to
    resolve once this point is reached.

    Suppose the target List's intent is Explore, Current, or Retired.
    Then this strips any sibling List first: same Category, a
    *different* one of those three intents. This is spec story 16.
    This is an auto-resolve, not a hard error. So moving a Star from
    Current to Retired (story 17) is one `tag` call. The user does not
    need to untag first.

    The resulting desired set is pushed via
    `client.update_list_membership_for_item` (or
    `update_list_membership_for_node` when `node_id` is supplied) in
    the same call. On a push failure for any other reason (network/API
    error, target List deleted concurrently), this raises
    `TagPushError` and writes no local state at all — mirrors
    `unstar_cmd`'s remote-first, write-only-on-success pattern. Only on
    a successful push are `stars.json`/`lists.json` updated.

    `lists`, if supplied, is trusted instead of a fresh
    `client.fetch_lists()` call -- see the design note above this
    module (ticket 19, scope 5: bulk-tagging N stars into the same
    List without N redundant live fetches). Every existing
    single-call-site caller omits it and gets the original
    fetch-every-time behavior, unchanged. Defensively re-classified
    (`classify_list`) either way, same reasoning as
    `ghstars.core.category`'s targets -- correct even if a caller passes
    a raw, unclassified fetch straight through. `apply_membership_diff`
    (below) updates a threaded `lists` snapshot after every successful
    push, so star N+1's remote-membership comparison above correctly
    sees star N's own already-applied change within the same batch.

    It does *not*, however, see a change some other process makes to
    star N+1 specifically while star N's push is still in flight — the
    threaded snapshot is only as fresh as the batch's own start-of-batch
    `fetch_lists()`, refined by this batch's own pushes, not re-verified
    against GitHub per star. A single `ghstars tag` call (no threaded
    `lists`) always compares against a fetch from that same call, so it
    does not have this gap. This is the same class of eventual-
    consistency trade ticket 07's fetch-fresh-skip-diverged design
    already accepts for List creation mid-batch (see the design note
    above this module) — accepted here for the same reason: closing it
    would mean a live `fetch_lists()` per star, which is exactly the
    round-trip cost `lists` threading exists to avoid.

    `node_id`, if supplied, is GitHub's pre-resolved opaque node ID for
    `full_name` — passed straight to
    `client.update_list_membership_for_node`, skipping the extra
    `full_name` -> node ID round trip `update_list_membership_for_item`
    would otherwise make. A bulk caller (the TUI's bulk-tag) resolves
    every target's node ID in one batched
    `client.resolve_repository_node_ids()` call up front and threads
    the result in here per star. Omitted (every other caller), this
    round trip happens the old way, unchanged.
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
            # Save newly created Lists before later validation or push steps.
            store.save_lists(lists)

        base_ids = star.list_ids
        remote_ids = [item.id for item in lists if full_name in item.items]
        if set(base_ids) != set(remote_ids):
            names_by_id = {item.id: item.name for item in lists}
            diverged = sorted(
                names_by_id.get(list_id, list_id)
                for list_id in set(base_ids) ^ set(remote_ids)
            )
            raise StarListMembershipDriftError(full_name, diverged)

        current, removed_list_ids = strip_lifecycle_siblings(
            base_ids, lists=lists, target=lst
        )
        new_ids = current if lst.id in current else [*current, lst.id]

        try:
            if node_id is not None:
                client.update_list_membership_for_node(node_id, new_ids)
            else:
                client.update_list_membership_for_item(full_name, new_ids)
        except Exception as exc:
            raise TagPushError(full_name, exc) from exc

        updated = star.model_copy(update={"list_ids": new_ids})
        store.save_stars([updated if s.full_name == full_name else s for s in stars])
        lists = apply_membership_diff(
            lists, full_name, old_ids=base_ids, new_ids=new_ids
        )
        store.save_lists(lists)
    return TagResult(star=updated, removed_list_ids=removed_list_ids, lists=lists)
