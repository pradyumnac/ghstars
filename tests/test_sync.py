from pathlib import Path

import pytest
from conftest import NOW, StarFactory

from ghstars.core.fake_client import FakeGitHubClient
from ghstars.core.models import List, RateLimitStatus, RetriageEntry
from ghstars.core.state_store import StateStore
from ghstars.core.sync import (
    RateLimitExceededError,
    archive_star,
    reconcile_list_membership,
    remove_star_from_lists,
    sync,
)


def test_sync_fetches_and_persists_stars(
    tmp_path: Path, make_star: StarFactory
) -> None:
    star = make_star()
    client = FakeGitHubClient(stars=[star])
    store = StateStore(tmp_path)

    result = sync(client, store)

    assert result.star_count == 1
    # Never-classified stars default into `Explore: General` (spec story 4,
    # see the default-classification tests below), so the saved record no
    # longer equals the fetched star byte-for-byte -- only `list_ids` moves.
    saved = store.load_stars()[0]
    assert saved == star.model_copy(update={"list_ids": saved.list_ids})
    assert saved.list_ids == [store.load_lists()[0].id]


def test_sync_raises_before_writing_when_rate_limited(
    tmp_path: Path, make_star: StarFactory
) -> None:
    client = FakeGitHubClient(
        stars=[make_star()],
        rate_limit=RateLimitStatus(remaining=0, limit=5000, ok=False),
    )
    store = StateStore(tmp_path)

    with pytest.raises(RateLimitExceededError):
        sync(client, store)

    assert store.load_stars() == []
    assert store.load_lists() == []


def test_sync_marks_a_repo_missing_from_fetch_as_archived(
    tmp_path: Path, make_star: StarFactory
) -> None:
    keep = make_star("pradyumnac/keep")
    gone = make_star(
        "pradyumnac/gone", language="Python", description="unstarred later"
    )
    store = StateStore(tmp_path)
    sync(FakeGitHubClient(stars=[keep, gone]), store)

    # `gone` was unstarred on GitHub since the last sync.
    result = sync(FakeGitHubClient(stars=[keep]), store)

    stars_by_name = {s.full_name: s for s in store.load_stars()}
    assert result.star_count == 2
    assert stars_by_name["pradyumnac/keep"].archived is False
    archived = stars_by_name["pradyumnac/gone"]
    assert archived.archived is True
    assert archived.archived_at is not None
    # Never deleted; last-known fields preserved (spec story 6).
    assert archived.language == "Python"
    assert archived.description == "unstarred later"
    assert archived.list_ids == []


def test_sync_does_not_refresh_archived_at_on_a_repeated_sync(
    tmp_path: Path, make_star: StarFactory
) -> None:
    gone = make_star("pradyumnac/gone")
    store = StateStore(tmp_path)
    sync(FakeGitHubClient(stars=[gone]), store)
    sync(FakeGitHubClient(stars=[]), store)
    first_archived_at = store.load_stars()[0].archived_at

    sync(FakeGitHubClient(stars=[]), store)
    second_archived_at = store.load_stars()[0].archived_at

    assert first_archived_at == second_archived_at


def test_sync_unarchives_a_restarred_repo(
    tmp_path: Path, make_star: StarFactory
) -> None:
    star = make_star("pradyumnac/back")
    store = StateStore(tmp_path)
    sync(FakeGitHubClient(stars=[star]), store)
    sync(FakeGitHubClient(stars=[]), store)
    assert store.load_stars()[0].archived is True

    # Re-starred on GitHub before the next sync.
    sync(FakeGitHubClient(stars=[star]), store)

    restarred = store.load_stars()[0]
    assert restarred.archived is False
    assert restarred.archived_at is None


def test_sync_self_heals_when_previous_state_is_corrupt(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """sync() reading stars.json to diff for unstars must not remove its
    prior ability to always overwrite a corrupted local snapshot."""
    store = StateStore(tmp_path)
    (store.base_dir / "stars.json").write_text("{not valid json")
    star = make_star()

    result = sync(FakeGitHubClient(stars=[star]), store)

    assert result.star_count == 1
    # Never-classified stars default into `Explore: General` (spec story 4).
    saved = store.load_stars()[0]
    assert saved == star.model_copy(update={"list_ids": saved.list_ids})
    assert saved.list_ids == [store.load_lists()[0].id]


def test_sync_fetches_and_classifies_lists(tmp_path: Path) -> None:
    lists = [
        List(id="L_1", name="Explore: Tool", slug="explore-tool"),
        List(id="L_2", name="Vendored skills", slug="vendored-skills"),
        List(id="L_3", name="Exploring: Foo", slug="exploring-foo"),
    ]
    client = FakeGitHubClient(lists=lists)
    store = StateStore(tmp_path)

    result = sync(client, store)

    assert result.list_count == 3
    saved = {lst.id: lst for lst in store.load_lists()}
    assert saved["L_1"].intent == "Explore"
    assert saved["L_1"].category == "Tool"
    assert saved["L_1"].malformed is False

    assert saved["L_2"].intent is None
    assert saved["L_2"].category is None
    assert saved["L_2"].malformed is False

    assert saved["L_3"].intent is None
    assert saved["L_3"].category is None
    assert saved["L_3"].malformed is True


def test_sync_pushes_a_pending_edit_when_only_local_changed(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Three-way merge scenario 1 (ticket 05): remote == base, so the
    pending local edit is the only real change since the last sync --
    push it. The push now runs *after* the fresh fetch/reconcile, not
    before (ticket 04's order), so this asserts the end result, not the
    old before-pull timing."""
    lst = List(id="L_1", name="Explore: Tool", slug="explore-tool")
    star = make_star("pradyumnac/ghstars", pending_list_ids=["L_1"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([lst])
    client = FakeGitHubClient(stars=[star], lists=[lst])

    result = sync(client, store)

    assert result.failed_tag_pushes == []
    saved = store.load_stars()[0]
    assert saved.list_ids == ["L_1"]
    assert saved.pending_list_ids is None
    # lists.json reflects the push too, without a second fetch round trip.
    assert store.load_lists()[0].items == ["pradyumnac/ghstars"]
    assert store.load_retriage() == []


def test_sync_leaves_remote_alone_when_local_pending_edit_matches_base(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Scenario 2: local == base (a no-op pending edit -- e.g. tagging a
    repo into a List it's already in). Whatever remote did since the last
    sync stands untouched; nothing is pushed."""
    a = List(id="L_1", name="Explore: A", slug="a")
    b = List(id="L_2", name="Explore: B", slug="b")
    star = make_star("pradyumnac/x", list_ids=["L_1"], pending_list_ids=["L_1"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([a, b])

    # Remote changed since: also added to L_2 on github.com.
    remote_star = star.model_copy(update={"pending_list_ids": None})
    a_remote = a.model_copy(update={"items": ["pradyumnac/x"]})
    b_remote = b.model_copy(update={"items": ["pradyumnac/x"]})
    client = FakeGitHubClient(stars=[remote_star], lists=[a_remote, b_remote])

    result = sync(client, store)

    assert result.failed_tag_pushes == []
    saved = store.load_stars()[0]
    assert sorted(saved.list_ids) == ["L_1", "L_2"]
    assert store.load_retriage() == []


def test_sync_noops_when_local_and_remote_converge_on_the_same_result(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Scenario 3: both local and remote moved away from base, but landed
    on the same result -- already effectively applied, so nothing is
    pushed again."""
    lst = List(id="L_1", name="Explore: Tool", slug="explore-tool")
    star = make_star("pradyumnac/x", pending_list_ids=["L_1"])  # base == []
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([lst])

    # Remote already shows the same membership the local edit wants.
    remote_lst = lst.model_copy(update={"items": ["pradyumnac/x"]})
    client = FakeGitHubClient(stars=[star], lists=[remote_lst])
    calls: list[tuple[str, list[str]]] = []
    original_push = client.update_list_membership_for_item

    def spy(item_id: str, list_ids: list[str]) -> None:
        calls.append((item_id, list_ids))
        original_push(item_id, list_ids)

    client.update_list_membership_for_item = spy  # type: ignore[method-assign]

    result = sync(client, store)

    assert calls == []  # never pushed -- already converged
    assert result.failed_tag_pushes == []
    saved = store.load_stars()[0]
    assert saved.list_ids == ["L_1"]
    assert saved.pending_list_ids is None
    assert store.load_retriage() == []


def test_sync_routes_a_conflicting_edit_to_the_retriage_queue_and_github_wins(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Scenario 4: local and remote both changed since base, to different
    results -- GitHub wins unconditionally (ADR 0001). The local edit is
    never pushed and never silently applied; it lands in the local-only
    Retriage Queue for the user to revisit."""
    base_lst = List(
        id="L_base", name="Explore: Base", slug="base", items=["pradyumnac/x"]
    )
    other_lst = List(id="L_other", name="Explore: Other", slug="other")
    remote_lst = List(id="L_remote", name="Explore: Remote", slug="remote")
    star = make_star("pradyumnac/x", list_ids=["L_base"], pending_list_ids=["L_other"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([base_lst, other_lst, remote_lst])

    # Remote reclassified the star into a *different* List since the last
    # sync, e.g. from the phone/web view.
    remote_star = star.model_copy(update={"pending_list_ids": None})
    base_remote = base_lst.model_copy(update={"items": []})
    remote_remote = remote_lst.model_copy(update={"items": ["pradyumnac/x"]})
    client = FakeGitHubClient(
        stars=[remote_star], lists=[base_remote, other_lst, remote_remote]
    )

    result = sync(client, store)

    assert result.failed_tag_pushes == []
    saved = store.load_stars()[0]
    assert saved.list_ids == ["L_remote"]  # GitHub's state wins
    assert saved.pending_list_ids is None

    queue = store.load_retriage()
    assert len(queue) == 1
    assert queue[0].star_full_name == "pradyumnac/x"
    assert queue[0].attempted_list_ids == ["L_other"]
    assert queue[0].resolved is False

    # Never pushed, never applied: the losing edit's target List stays
    # untouched.
    by_id = {lst.id: lst for lst in store.load_lists()}
    assert by_id["L_other"].items == []


def test_sync_persists_the_retriage_queue_before_stars_and_lists(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Durability: the Retriage Queue write must land before stars.json/
    lists.json. Those two already reflect the pending edit cleared (a
    fresh `fetch_stars()` never carries `pending_list_ids`), so if the
    process dies between the two writes, the losing edit's own record
    must not be the one that's missing -- ticket 05 requires it is
    "never discarded." """
    base_lst = List(
        id="L_base", name="Explore: Base", slug="base", items=["pradyumnac/x"]
    )
    other_lst = List(id="L_other", name="Explore: Other", slug="other")
    remote_lst = List(id="L_remote", name="Explore: Remote", slug="remote")
    star = make_star("pradyumnac/x", list_ids=["L_base"], pending_list_ids=["L_other"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([base_lst, other_lst, remote_lst])

    remote_star = star.model_copy(update={"pending_list_ids": None})
    base_remote = base_lst.model_copy(update={"items": []})
    remote_remote = remote_lst.model_copy(update={"items": ["pradyumnac/x"]})
    client = FakeGitHubClient(
        stars=[remote_star], lists=[base_remote, other_lst, remote_remote]
    )

    class _Boom(Exception):
        pass

    def _explode(*_args: object, **_kwargs: object) -> None:
        raise _Boom

    store.save_stars = _explode  # type: ignore[method-assign]

    with pytest.raises(_Boom):
        sync(client, store)

    # A fresh StateStore over the same directory, since the one above had
    # save_stars swapped out.
    queue = StateStore(tmp_path).load_retriage()
    assert len(queue) == 1
    assert queue[0].star_full_name == "pradyumnac/x"


def test_sync_appends_new_conflicts_to_an_existing_retriage_queue(
    tmp_path: Path,
) -> None:
    """The Retriage Queue accumulates across syncs -- an unresolved entry
    from a prior sync must not be silently dropped by a later one that
    finds nothing new to add."""
    store = StateStore(tmp_path)
    existing = RetriageEntry(
        star_full_name="pradyumnac/old-conflict",
        attempted_list_ids=["L_x"],
        conflict_detected_at=NOW,
    )
    store.save_retriage([existing])

    sync(FakeGitHubClient(), store)  # nothing to sync, no new conflicts

    assert store.load_retriage() == [existing]


def test_sync_drops_a_moot_pending_edit_when_the_star_was_unstarred_first(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """A star can be tagged, then unstarred on GitHub before the next
    sync runs. `_carry_forward_archived` already clears `pending_list_ids`
    via `archive_star()` for it, before the merge ever looks at it -- the
    stale edit is silently moot, not a failure and not a conflict: there
    is nothing left to arbitrate for a repo that's no longer starred."""
    keep_lst = List(id="L_1", name="Explore: Keep", slug="keep")
    kept = make_star("pradyumnac/kept", pending_list_ids=["L_1"])
    gone = make_star("pradyumnac/gone", pending_list_ids=["L_1"])
    store = StateStore(tmp_path)
    store.save_stars([kept, gone])
    store.save_lists([keep_lst])
    client = FakeGitHubClient(stars=[kept, gone], lists=[keep_lst])
    client.remove_star("pradyumnac/gone")  # unstarred since it was tagged

    result = sync(client, store)  # must not raise

    assert result.failed_tag_pushes == []
    by_name = {s.full_name: s for s in store.load_stars()}
    assert by_name["pradyumnac/kept"].list_ids == ["L_1"]
    assert by_name["pradyumnac/kept"].pending_list_ids is None
    assert by_name["pradyumnac/gone"].pending_list_ids is None
    assert by_name["pradyumnac/gone"].archived is True
    assert by_name["pradyumnac/gone"].list_ids == []
    assert store.load_retriage() == []


def test_sync_reports_a_genuine_push_failure_and_keeps_going(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """A pending edit can reference a List that was deleted on GitHub
    since it was staged. Unlike the moot-edit case above, the star is
    still starred (remote == base on the List axis, so the merge decides
    to push) -- the client raises, and that one star's failure must not
    abort the sync or the merge for anything else."""
    keep_lst = List(id="L_1", name="Explore: Keep", slug="keep")
    kept = make_star("pradyumnac/kept", pending_list_ids=["L_1"])
    broken = make_star("pradyumnac/broken", pending_list_ids=["L_deleted"])
    store = StateStore(tmp_path)
    store.save_stars([kept, broken])
    store.save_lists([keep_lst])
    # "L_deleted" was removed on GitHub since pradyumnac/broken was tagged
    # into it -- the fake models that by simply never knowing about it.
    client = FakeGitHubClient(stars=[kept, broken], lists=[keep_lst])

    result = sync(client, store)  # must not raise

    assert result.failed_tag_pushes == ["pradyumnac/broken"]
    by_name = {s.full_name: s for s in store.load_stars()}
    assert by_name["pradyumnac/kept"].list_ids == ["L_1"]
    assert by_name["pradyumnac/broken"].pending_list_ids is None
    # Still unclassified after the failed tag push, but the default-
    # classification step (spec story 4) must NOT also claim it: the
    # star still carries a genuine failed user tag intent, not "never
    # classified by anyone" -- defaulting it would silently paper over
    # that failure with an unrelated List instead of leaving it for the
    # "re-run `ghstars tag`" message to actually be correct about.
    assert by_name["pradyumnac/broken"].list_ids == []
    assert result.failed_default_pushes == []
    assert store.load_retriage() == []


def test_sync_populates_list_ids_from_list_membership(
    tmp_path: Path, make_star: StarFactory
) -> None:
    shared = make_star("pradyumnac/shared")
    solo = make_star("pradyumnac/solo")
    unlisted = make_star("pradyumnac/unlisted")
    lists = [
        List(id="L_1", name="Explore: A", slug="a", items=["pradyumnac/shared"]),
        List(
            id="L_2",
            name="Explore: B",
            slug="b",
            items=["pradyumnac/shared", "pradyumnac/solo"],
        ),
    ]
    client = FakeGitHubClient(stars=[shared, solo, unlisted], lists=lists)
    store = StateStore(tmp_path)

    sync(client, store)

    by_name = {s.full_name: s for s in store.load_stars()}
    assert sorted(by_name["pradyumnac/shared"].list_ids) == ["L_1", "L_2"]
    assert by_name["pradyumnac/solo"].list_ids == ["L_2"]
    # Not in any List after reconcile -- defaults into `Explore: General`
    # (spec story 4), rather than staying unclassified.
    explore_general = next(
        lst for lst in store.load_lists() if lst.name == "Explore: General"
    )
    assert by_name["pradyumnac/unlisted"].list_ids == [explore_general.id]


def test_reconcile_list_membership_never_relists_an_archived_star(
    make_star: StarFactory,
) -> None:
    """A stale/racy List.items entry for an already-archived star must not
    override archive_star()'s empty list_ids (CONTEXT.md: Archived carries
    no List membership going forward)."""
    archived = archive_star(make_star("pradyumnac/gone"), now=NOW)
    lists = [
        List(id="L_1", name="Explore: A", slug="a", items=["pradyumnac/gone"]),
    ]

    reconciled = reconcile_list_membership([archived], lists)

    assert reconciled[0].list_ids == []
    assert reconciled[0].archived is True


def test_reconcile_list_membership_skips_a_list_item_with_no_matching_star(
    make_star: StarFactory,
) -> None:
    """The two fetches are not one atomic snapshot (see
    docs/explanation/known-limitations.md) -- an unmatched item must not
    raise, only be skipped."""
    known = make_star("pradyumnac/known")
    lists = [
        List(
            id="L_1",
            name="Explore: A",
            slug="a",
            items=["pradyumnac/known", "pradyumnac/not-yet-fetched"],
        ),
    ]

    reconciled = reconcile_list_membership([known], lists)

    assert reconciled[0].list_ids == ["L_1"]


def test_remove_star_from_lists_drops_only_the_matching_star() -> None:
    lists = [
        List(id="L_1", name="Explore: A", slug="a", items=["x/y", "a/b"]),
        List(id="L_2", name="Explore: B", slug="b", items=["a/b"]),
        List(id="L_3", name="Explore: C", slug="c", items=[]),
    ]

    updated = remove_star_from_lists(lists, "a/b")

    by_id = {lst.id: lst for lst in updated}
    assert by_id["L_1"].items == ["x/y"]
    assert by_id["L_2"].items == []
    assert by_id["L_3"].items == []


def test_sync_defaults_a_never_classified_star_into_explore_general(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Spec story 4: a star with no real classification lands in
    `Explore: General`, created for real (public by default, story 48)
    since it doesn't exist yet."""
    star = make_star("pradyumnac/unclassified")
    client = FakeGitHubClient(stars=[star])
    store = StateStore(tmp_path)

    result = sync(client, store)

    assert result.failed_default_pushes == []
    saved_lists = store.load_lists()
    assert len(saved_lists) == 1
    assert saved_lists[0].name == "Explore: General"
    assert saved_lists[0].intent == "Explore"
    assert saved_lists[0].category == "General"
    assert saved_lists[0].is_private is False
    assert saved_lists[0].items == ["pradyumnac/unclassified"]
    assert store.load_stars()[0].list_ids == [saved_lists[0].id]


def test_sync_creates_explore_general_only_once_for_several_unclassified_stars(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Several never-classified stars in the same sync must share one
    `Explore: General` List, not one each."""
    stars = [make_star(f"pradyumnac/star-{i}") for i in range(3)]
    client = FakeGitHubClient(stars=stars)
    store = StateStore(tmp_path)

    result = sync(client, store)

    assert result.failed_default_pushes == []
    saved_lists = store.load_lists()
    assert len(saved_lists) == 1
    assert saved_lists[0].name == "Explore: General"
    assert sorted(saved_lists[0].items) == [
        "pradyumnac/star-0",
        "pradyumnac/star-1",
        "pradyumnac/star-2",
    ]
    for star in store.load_stars():
        assert star.list_ids == [saved_lists[0].id]


def test_sync_reuses_an_existing_explore_general_list_across_syncs(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """A second sync must not create a duplicate `Explore: General` List
    -- lazy creation is idempotent across syncs, not just within one."""
    first = make_star("pradyumnac/first")
    store = StateStore(tmp_path)
    sync(FakeGitHubClient(stars=[first]), store)
    explore_general = store.load_lists()[0]

    second = make_star("pradyumnac/second")
    client = FakeGitHubClient(
        stars=[first, second],
        lists=[explore_general.model_copy(update={"items": [first.full_name]})],
    )
    sync(client, store)

    saved_lists = store.load_lists()
    assert len(saved_lists) == 1
    assert saved_lists[0].id == explore_general.id
    assert sorted(saved_lists[0].items) == ["pradyumnac/first", "pradyumnac/second"]


def test_sync_isolates_a_default_push_failure_and_reports_it(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """One star's default-classification push failing must not abort
    the default-classification step for any other unclassified star, or
    the sync as a whole."""
    ok = make_star("pradyumnac/ok")
    broken = make_star("pradyumnac/broken")
    client = FakeGitHubClient(stars=[ok, broken])

    original_push = client.update_list_membership_for_item

    def flaky_push(item_id: str, list_ids: list[str]) -> None:
        if item_id == "pradyumnac/broken":
            raise RuntimeError("boom")
        original_push(item_id, list_ids)

    client.update_list_membership_for_item = flaky_push  # type: ignore[method-assign]
    store = StateStore(tmp_path)

    result = sync(client, store)  # must not raise

    assert result.failed_default_pushes == ["pradyumnac/broken"]
    by_name = {s.full_name: s for s in store.load_stars()}
    saved_lists = store.load_lists()
    assert len(saved_lists) == 1  # the List is still created, just once
    assert by_name["pradyumnac/ok"].list_ids == [saved_lists[0].id]
    assert by_name["pradyumnac/broken"].list_ids == []


def test_sync_does_not_default_a_star_that_just_lost_a_merge_conflict(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """A star whose pending edit just lost a three-way merge conflict
    can also have empty `list_ids` here, if remote itself was empty --
    but ticket 05 promises the losing edit is "never applied." The
    default-classification step (spec story 4) must not apply a
    *different* edit to it in the same sync; that would break the same
    promise a different way."""
    other_lst = List(id="L_other", name="Explore: Other", slug="other")
    remote_lst = List(id="L_remote", name="Explore: Remote", slug="remote")
    # base: star was in no List. local: staged into L_other. remote: has
    # since been staged into L_remote by someone else -- both sides moved
    # away from base, to different results, so this is a conflict.
    star = make_star("pradyumnac/x", pending_list_ids=["L_other"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([other_lst, remote_lst])

    remote_star = star.model_copy(update={"pending_list_ids": None})
    remote_remote = remote_lst.model_copy(update={"items": ["pradyumnac/x"]})
    client = FakeGitHubClient(stars=[remote_star], lists=[other_lst, remote_remote])

    result = sync(client, store)

    assert result.failed_default_pushes == []
    saved = store.load_stars()[0]
    # GitHub's state wins per ticket 05 -- but remote's actual result
    # here (L_remote) is not empty, so this asserts the star was never
    # touched by the default step at all: no "Explore: General" List
    # was created just for a star the merge already resolved.
    assert saved.list_ids == ["L_remote"]
    assert not any(lst.name == "Explore: General" for lst in store.load_lists())
    queue = store.load_retriage()
    assert len(queue) == 1
    assert queue[0].star_full_name == "pradyumnac/x"


def test_sync_isolates_explore_general_creation_failure(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """If creating the `Explore: General` List itself fails, every
    unclassified star's default push must be reported as failed, and
    the failure must not propagate out of `sync()` and lose progress
    already computed earlier in the same call (e.g. a successful tag
    push)."""
    keep_lst = List(id="L_1", name="Explore: Keep", slug="keep")
    kept = make_star("pradyumnac/kept", pending_list_ids=["L_1"])
    unclassified = make_star("pradyumnac/unclassified")
    store = StateStore(tmp_path)
    store.save_stars([kept, unclassified])
    store.save_lists([keep_lst])
    client = FakeGitHubClient(stars=[kept, unclassified], lists=[keep_lst])

    def broken_create_list(
        name: str, *, is_private: bool = False, description: str | None = None
    ) -> List:
        raise RuntimeError("boom")

    client.create_list = broken_create_list  # type: ignore[method-assign]

    result = sync(client, store)  # must not raise

    assert result.failed_default_pushes == ["pradyumnac/unclassified"]
    # The earlier, unrelated tag push still succeeded and was persisted --
    # the List-creation failure did not unwind the whole sync.
    assert result.failed_tag_pushes == []
    by_name = {s.full_name: s for s in store.load_stars()}
    assert by_name["pradyumnac/kept"].list_ids == ["L_1"]
    assert by_name["pradyumnac/unclassified"].list_ids == []
    saved_lists = store.load_lists()
    assert len(saved_lists) == 1
    assert saved_lists[0].id == "L_1"
    assert saved_lists[0].items == ["pradyumnac/kept"]  # the earlier push's effect
