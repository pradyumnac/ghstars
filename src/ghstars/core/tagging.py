from pydantic import BaseModel

from ghstars.core.github_client import GitHubClient
from ghstars.core.models import List, Star
from ghstars.core.state_store import StateStore
from ghstars.core.sync import apply_membership_diff
from ghstars.core.taxonomy import classify_list, strip_lifecycle_siblings
from ghstars.github import GitHubApiError

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
    """Add `full_name` to `list_name`, then push the change to GitHub.

    Create the List when GitHub does not already have it. Read live
    GitHub state to decide that, never the local cache. A stale cache
    can create a duplicate List.

    Raise `StarListMembershipDriftError` when the star's local
    `list_ids` disagree with its membership in the same `fetch_lists()`
    result. Push nothing and write nothing. The user must run `ghstars
    sync` first, then retry.

    Strip a sibling List when the target List's intent is Explore,
    Current, or Retired. A sibling holds the same Category under one of
    the other two intents. This makes a Current-to-Retired move one
    call (spec stories 16 and 17).

    Raise `TagPushError` when the push fails, and write no local state.
    Update `stars.json` and `lists.json` only after the push succeeds.

    Args:
        lists: a List snapshot to trust in place of a fresh
            `client.fetch_lists()` call. A bulk caller threads one
            snapshot through every star, to avoid one fetch per star.
            `apply_membership_diff` updates it after each push. See
            `docs/explanation/known-limitations.md` for the staleness
            this accepts.
        node_id: GitHub's node ID for `full_name`. Skips the lookup
            that `update_list_membership_for_item` makes. A bulk caller
            resolves every ID in one `resolve_repository_node_ids()`
            call.
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


class BulkTagOutcome(BaseModel):
    """One repository's outcome from `bulk_tag_stars()`.

    Exactly one of `result` and `error` is set. Reporting a full list of
    outcomes -- one per requested `full_name`, in the same order -- lets
    a caller tell which targets succeeded and which failed without a
    batch-wide exception hiding the rest (ticket 31, Scope C).
    """

    full_name: str
    result: TagResult | None = None
    error: str | None = None


def bulk_tag_stars(
    client: GitHubClient,
    store: StateStore,
    full_names: list[str],
    list_name: str,
    *,
    is_private: bool = False,
) -> list[BulkTagOutcome]:
    """Tag every repo in `full_names` into `list_name`, one `tag_star()`
    call per repo, isolating each repo's failure from the others.

    Moved from the TUI's `_apply_tag` (ticket 19, scope 5; ticket 31,
    Scope C) so the CLI can reuse the same orchestration. Preserves that
    method's exact trade-offs:

    Catches every exception, not just the documented
    `StarNotFoundError`/`StarArchivedError`/`GitHubApiError`. A caller
    running this off the UI thread (or any thread) needs every repo's
    unexpected failure (a `filelock.Timeout` from a concurrent
    `ghstars` process holding the store's lock, for instance) reported
    per-repo rather than escaping and losing the rest of the batch.

    Bulk-tagging N Stars into the same List used to cost N redundant
    `fetch_lists()` calls -- `tag_star()` re-fetched every List from
    GitHub on every call, by design, to check live state before
    creating a List. Fixed in ticket 19 (scope 5): `tag_star()` accepts
    an optional pre-fetched `lists` snapshot, and returns the (possibly
    List-creation-updated) snapshot it used on `TagResult.lists`. This
    loop seeds `lists` as `None` for the first star (identical behavior
    to before: a real fetch) and threads each result's `lists` into the
    next call, so the whole batch shares at most one live
    `fetch_lists()` round trip instead of paying it per star.
    Trade-off: `tag_star()`'s drift check (ticket 16) for star N+1 sees
    star N's own already-applied change correctly, but not a change
    some other process makes directly to star N+1 while star N's push
    is still in flight -- see the caveat on `tag_star()`'s own
    docstring. A single-item call never threads `lists`, so it does not
    have this gap.

    `tag_star()` also pushes each star to GitHub immediately (ticket
    16), which needs GitHub's node ID per star. For more than one
    target, this resolves every target's node ID in one batched
    `resolve_repository_node_ids()` call up front rather than paying
    `tag_star()`'s internal one-round-trip-per-star resolution N times
    -- see docs/explanation/known-limitations.md. A single target skips
    this (no batching win for one repo). A `full_name` missing from the
    batch result (lookup failed, or the repo was renamed/deleted) just
    falls back to `tag_star()`'s own resolution for that one star --
    isolated the same way a push failure already is below, not a
    reason to fail the whole batch. The membership-update pushes
    themselves stay sequential, one per star, preserving this
    function's per-star failure isolation.
    """
    outcomes: list[BulkTagOutcome] = []
    lists: list[List] | None = None
    node_ids: dict[str, str] = {}
    if len(full_names) > 1:
        try:
            node_ids = client.resolve_repository_node_ids(full_names)
        except Exception:  # noqa: BLE001 -- batching is an optimization.
            node_ids = {}
    for full_name in full_names:
        try:
            result = tag_star(
                client,
                store,
                full_name,
                list_name,
                is_private=is_private,
                lists=lists,
                node_id=node_ids.get(full_name),
            )
        except (
            StarNotFoundError,
            StarArchivedError,
            StarListMembershipDriftError,
            TagPushError,
            GitHubApiError,
        ) as exc:
            outcomes.append(BulkTagOutcome(full_name=full_name, error=str(exc)))
            continue
        except Exception as exc:  # noqa: BLE001 -- see docstring above
            outcomes.append(
                BulkTagOutcome(full_name=full_name, error=f"unexpected error: {exc}")
            )
            continue
        lists = result.lists
        outcomes.append(BulkTagOutcome(full_name=full_name, result=result))
    return outcomes
