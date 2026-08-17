from pathlib import Path

import pytest
from conftest import StarFactory

from ghstars.core.category import (
    CategoryNotFoundError,
    InvalidCategoryNameError,
    drain_category,
    rename_category,
)
from ghstars.core.fake_client import FakeGitHubClient
from ghstars.core.models import List
from ghstars.core.state_store import StateStore

# --- rename_category ---------------------------------------------------


def test_rename_category_renames_all_lifecycle_intent_variants(tmp_path: Path) -> None:
    explore = List(id="L_explore", name="Explore: Old", slug="explore-old")
    current = List(id="L_current", name="Current: Old", slug="current-old")
    retired = List(id="L_retired", name="Retired: Old", slug="retired-old")
    unrelated = List(id="L_other", name="Explore: Other", slug="explore-other")
    lists = [explore, current, retired, unrelated]
    store = StateStore(tmp_path)
    store.save_lists(lists)
    client = FakeGitHubClient(lists=lists)

    result = rename_category(client, store, "Old", "New")

    assert sorted(result.renamed) == ["L_current", "L_explore", "L_retired"]
    assert result.skipped == []

    fresh_by_id = {lst.id: lst for lst in client.fetch_lists()}
    assert fresh_by_id["L_explore"].name == "Explore: New"
    assert fresh_by_id["L_current"].name == "Current: New"
    assert fresh_by_id["L_retired"].name == "Retired: New"
    assert fresh_by_id["L_other"].name == "Explore: Other"  # untouched

    saved_by_id = {lst.id: lst for lst in store.load_lists()}
    assert saved_by_id["L_explore"].category == "New"
    assert saved_by_id["L_explore"].intent == "Explore"
    assert saved_by_id["L_explore"].malformed is False


def test_rename_category_does_not_touch_reference_or_general_lists(
    tmp_path: Path,
) -> None:
    explore = List(id="L_explore", name="Explore: Old", slug="explore-old")
    reference = List(id="L_ref", name="Reference: Old", slug="reference-old")
    general = List(id="L_general", name="Old", slug="old")
    lists = [explore, reference, general]
    store = StateStore(tmp_path)
    store.save_lists(lists)
    client = FakeGitHubClient(lists=lists)

    result = rename_category(client, store, "Old", "New")

    assert result.renamed == ["L_explore"]
    fresh_by_id = {lst.id: lst for lst in client.fetch_lists()}
    assert fresh_by_id["L_ref"].name == "Reference: Old"
    assert fresh_by_id["L_general"].name == "Old"


def test_rename_category_skips_a_list_renamed_on_github_since_the_last_sync(
    tmp_path: Path,
) -> None:
    stale_local = List(id="L_explore", name="Explore: Old", slug="explore-old")
    store = StateStore(tmp_path)
    store.save_lists([stale_local])
    # Live GitHub state has already moved on -- someone renamed it
    # concurrently, since the local snapshot was taken.
    live = List(id="L_explore", name="Explore: SomethingElse", slug="explore-x")
    client = FakeGitHubClient(lists=[live])

    result = rename_category(client, store, "Old", "New")

    assert result.renamed == []
    assert result.skipped == ["L_explore"]
    assert client.fetch_lists()[0].name == "Explore: SomethingElse"  # untouched


def test_rename_category_skips_a_list_deleted_on_github_since_the_last_sync(
    tmp_path: Path,
) -> None:
    stale_local = List(id="L_explore", name="Explore: Old", slug="explore-old")
    store = StateStore(tmp_path)
    store.save_lists([stale_local])
    client = FakeGitHubClient(lists=[])  # deleted concurrently

    result = rename_category(client, store, "Old", "New")

    assert result.renamed == []
    assert result.skipped == ["L_explore"]


def test_rename_category_skips_when_the_destination_name_already_exists(
    tmp_path: Path,
) -> None:
    old = List(id="L_old", name="Explore: Old", slug="explore-old")
    new = List(id="L_new", name="Explore: New", slug="explore-new")
    lists = [old, new]
    store = StateStore(tmp_path)
    store.save_lists(lists)
    client = FakeGitHubClient(lists=lists)

    result = rename_category(client, store, "Old", "New")

    assert result.renamed == []
    assert result.skipped == ["L_old"]
    assert client.fetch_lists() == lists  # nothing changed, no duplicate name


def test_rename_category_raises_when_no_local_lists_match_the_old_category(
    tmp_path: Path,
) -> None:
    store = StateStore(tmp_path)
    client = FakeGitHubClient()

    with pytest.raises(CategoryNotFoundError):
        rename_category(client, store, "Nonexistent", "New")


def test_rename_category_is_a_no_op_when_old_equals_new(tmp_path: Path) -> None:
    lst = List(id="L_explore", name="Explore: Old", slug="explore-old")
    store = StateStore(tmp_path)
    store.save_lists([lst])
    client = FakeGitHubClient(lists=[lst])

    result = rename_category(client, store, "Old", "Old")

    assert result.renamed == []
    assert result.skipped == []
    assert client.fetch_lists()[0].name == "Explore: Old"


@pytest.mark.parametrize(("old", "new"), [("", "New"), ("Old", ""), ("  ", "New")])
def test_rename_category_rejects_blank_names(
    tmp_path: Path, old: str, new: str
) -> None:
    store = StateStore(tmp_path)
    client = FakeGitHubClient()

    with pytest.raises(InvalidCategoryNameError):
        rename_category(client, store, old, new)


# --- drain_category ------------------------------------------------------


def test_drain_category_migrates_stars_matching_their_existing_intent(
    tmp_path: Path, make_star: StarFactory
) -> None:
    explore_old = List(
        id="L_explore_old", name="Explore: Old", slug="explore-old", items=["a/a"]
    )
    current_old = List(
        id="L_current_old", name="Current: Old", slug="current-old", items=["a/b"]
    )
    star_a = make_star("a/a", list_ids=["L_explore_old"])
    star_b = make_star("a/b", list_ids=["L_current_old"])
    lists = [explore_old, current_old]
    stars = [star_a, star_b]
    store = StateStore(tmp_path)
    store.save_lists(lists)
    store.save_stars(stars)
    client = FakeGitHubClient(stars=stars, lists=lists)

    result = drain_category(client, store, "Old", "New")

    assert sorted(result.migrated) == ["a/a", "a/b"]
    assert result.skipped == []

    fresh_lists = {lst.name: lst for lst in client.fetch_lists()}
    assert set(fresh_lists["Explore: New"].items) == {"a/a"}
    assert set(fresh_lists["Current: New"].items) == {"a/b"}
    assert fresh_lists["Explore: Old"].items == []
    assert fresh_lists["Current: Old"].items == []

    fresh_stars = {star.full_name: star for star in client.fetch_stars()}
    assert fresh_stars["a/a"].list_ids == [fresh_lists["Explore: New"].id]
    assert fresh_stars["a/b"].list_ids == [fresh_lists["Current: New"].id]

    saved_stars = {star.full_name: star for star in store.load_stars()}
    assert saved_stars["a/a"].list_ids == [fresh_lists["Explore: New"].id]


def test_drain_category_creates_destination_lists_public_by_default(
    tmp_path: Path, make_star: StarFactory
) -> None:
    explore_old = List(id="L_1", name="Explore: Old", slug="explore-old", items=["a/a"])
    star = make_star("a/a", list_ids=["L_1"])
    store = StateStore(tmp_path)
    store.save_lists([explore_old])
    store.save_stars([star])
    client = FakeGitHubClient(stars=[star], lists=[explore_old])

    drain_category(client, store, "Old", "New")

    created = next(lst for lst in client.fetch_lists() if lst.name == "Explore: New")
    assert created.is_private is False


def test_drain_category_creates_destination_lists_private_when_requested(
    tmp_path: Path, make_star: StarFactory
) -> None:
    explore_old = List(id="L_1", name="Explore: Old", slug="explore-old", items=["a/a"])
    star = make_star("a/a", list_ids=["L_1"])
    store = StateStore(tmp_path)
    store.save_lists([explore_old])
    store.save_stars([star])
    client = FakeGitHubClient(stars=[star], lists=[explore_old])

    drain_category(client, store, "Old", "New", is_private=True)

    created = next(lst for lst in client.fetch_lists() if lst.name == "Explore: New")
    assert created.is_private is True


def test_drain_category_reuses_an_existing_destination_list(
    tmp_path: Path, make_star: StarFactory
) -> None:
    explore_old = List(
        id="L_old", name="Explore: Old", slug="explore-old", items=["a/a"]
    )
    explore_new = List(
        id="L_new", name="Explore: New", slug="explore-new", items=["a/existing"]
    )
    star_a = make_star("a/a", list_ids=["L_old"])
    star_existing = make_star("a/existing", list_ids=["L_new"])
    lists = [explore_old, explore_new]
    stars = [star_a, star_existing]
    store = StateStore(tmp_path)
    store.save_lists(lists)
    store.save_stars(stars)
    client = FakeGitHubClient(stars=stars, lists=lists)

    result = drain_category(client, store, "Old", "New")

    assert result.migrated == ["a/a"]
    fresh_lists = client.fetch_lists()
    assert len(fresh_lists) == 2  # no duplicate "Explore: New" created
    new_list = next(lst for lst in fresh_lists if lst.name == "Explore: New")
    assert set(new_list.items) == {"a/a", "a/existing"}


def test_drain_category_skips_a_star_removed_from_the_source_list_since_the_snapshot(
    tmp_path: Path, make_star: StarFactory
) -> None:
    # Local snapshot (what triggered the drain) still lists both.
    stale_local = List(
        id="L_1", name="Explore: Old", slug="explore-old", items=["a/a", "a/b"]
    )
    store = StateStore(tmp_path)
    store.save_lists([stale_local])
    star_a = make_star("a/a", list_ids=["L_1"])
    star_b = make_star("a/b", list_ids=[])  # already removed live
    store.save_stars([star_a, star_b])
    # Live GitHub state: a/b already left the source List.
    live = List(id="L_1", name="Explore: Old", slug="explore-old", items=["a/a"])
    client = FakeGitHubClient(stars=[star_a, star_b], lists=[live])

    result = drain_category(client, store, "Old", "New")

    assert result.migrated == ["a/a"]
    assert result.skipped == ["a/b"]


def test_drain_category_skips_a_star_unstarred_since_the_snapshot(
    tmp_path: Path, make_star: StarFactory
) -> None:
    stale_local = List(id="L_1", name="Explore: Old", slug="explore-old", items=["a/a"])
    store = StateStore(tmp_path)
    store.save_lists([stale_local])
    star = make_star("a/a", list_ids=["L_1"])
    store.save_stars([star])
    # Live: the repo was unstarred entirely -- gone from fetch_stars().
    live = List(id="L_1", name="Explore: Old", slug="explore-old", items=["a/a"])
    client = FakeGitHubClient(stars=[], lists=[live])

    result = drain_category(client, store, "Old", "New")

    assert result.migrated == []
    assert result.skipped == ["a/a"]


def test_drain_category_skips_all_targets_when_the_source_list_was_deleted(
    tmp_path: Path, make_star: StarFactory
) -> None:
    stale_local = List(id="L_1", name="Explore: Old", slug="explore-old", items=["a/a"])
    store = StateStore(tmp_path)
    store.save_lists([stale_local])
    star = make_star("a/a", list_ids=["L_1"])
    store.save_stars([star])
    client = FakeGitHubClient(stars=[star], lists=[])  # deleted concurrently

    result = drain_category(client, store, "Old", "New")

    assert result.migrated == []
    assert result.skipped == ["a/a"]
    assert client.fetch_lists() == []  # no destination List created either


def test_drain_category_raises_when_no_local_lists_match_the_from_category(
    tmp_path: Path,
) -> None:
    store = StateStore(tmp_path)
    client = FakeGitHubClient()

    with pytest.raises(CategoryNotFoundError):
        drain_category(client, store, "Nonexistent", "New")


def test_drain_category_is_a_no_op_when_from_equals_to(
    tmp_path: Path, make_star: StarFactory
) -> None:
    lst = List(id="L_1", name="Explore: Old", slug="explore-old", items=["a/a"])
    star = make_star("a/a", list_ids=["L_1"])
    store = StateStore(tmp_path)
    store.save_lists([lst])
    store.save_stars([star])
    client = FakeGitHubClient(stars=[star], lists=[lst])

    result = drain_category(client, store, "Old", "Old")

    assert result.migrated == []
    assert result.skipped == []


@pytest.mark.parametrize(("frm", "to"), [("", "New"), ("Old", ""), ("  ", "New")])
def test_drain_category_rejects_blank_names(tmp_path: Path, frm: str, to: str) -> None:
    store = StateStore(tmp_path)
    client = FakeGitHubClient()

    with pytest.raises(InvalidCategoryNameError):
        drain_category(client, store, frm, to)


def test_drain_category_strips_a_conflicting_sibling_intent_at_the_destination(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Spec story 16: migrating a Star into `to_category` must not leave
    it in two lifecycle Lists under that Category at once, even when
    the conflict is with a List that predates the drain entirely."""
    explore_old = List(
        id="L_explore_old", name="Explore: Old", slug="explore-old", items=["a/a"]
    )
    current_new = List(
        id="L_current_new", name="Current: New", slug="current-new", items=["a/a"]
    )
    star = make_star("a/a", list_ids=["L_explore_old", "L_current_new"])
    lists = [explore_old, current_new]
    store = StateStore(tmp_path)
    store.save_lists(lists)
    store.save_stars([star])
    client = FakeGitHubClient(stars=[star], lists=lists)

    result = drain_category(client, store, "Old", "New")

    assert result.migrated == ["a/a"]
    fresh_lists = {lst.name: lst for lst in client.fetch_lists()}
    explore_new = fresh_lists["Explore: New"]
    assert "a/a" in explore_new.items
    assert "a/a" not in fresh_lists["Current: New"].items  # sibling stripped

    fresh_star = client.fetch_stars()[0]
    assert fresh_star.list_ids == [explore_new.id]


def test_drain_category_never_touches_an_unrelated_stars_local_state(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """`drain_category()` reads fresh Stars from `client.fetch_stars()` to
    compute the migration, but must never persist that fresh snapshot
    wholesale -- `fetch_stars()` always resets `pending_list_ids` to
    `None` and `archived` to `False` (real client and fake alike), so a
    blind overwrite would silently wipe every OTHER star's staged
    `ghstars tag` edit and Archived history, not just the ones this
    drain actually touches."""
    explore_old = List(
        id="L_explore_old", name="Explore: Old", slug="explore-old", items=["a/a"]
    )
    migrated_star = make_star("a/a", list_ids=["L_explore_old"])
    # Unrelated star: a real staged `ghstars tag` edit not yet pushed.
    tagged_star = make_star("a/tagged", pending_list_ids=["L_somewhere_else"])
    # Unrelated star: Archived locally (unstarred on GitHub already).
    archived_star = make_star("a/archived", archived=True, list_ids=[])
    lists = [explore_old]
    store = StateStore(tmp_path)
    store.save_lists(lists)
    store.save_stars([migrated_star, tagged_star, archived_star])
    # Only the migrated star is known to the fake GitHub client -- the
    # tagged/archived stars stay purely local, same as a real account
    # where `fetch_stars()` never returns Archived repos or local-only
    # `pending_list_ids`.
    client = FakeGitHubClient(stars=[migrated_star], lists=lists)

    result = drain_category(client, store, "Old", "New")

    assert result.migrated == ["a/a"]
    saved_by_name = {star.full_name: star for star in store.load_stars()}
    assert saved_by_name["a/tagged"].pending_list_ids == ["L_somewhere_else"]
    assert saved_by_name["a/archived"].archived is True
    assert saved_by_name["a/a"].list_ids != ["L_explore_old"]  # actually migrated
