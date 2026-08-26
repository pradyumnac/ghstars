from pathlib import Path

import pytest
from conftest import StarFactory

from ghstars.core.fake_client import FakeGitHubClient
from ghstars.core.models import List
from ghstars.core.state_store import StateStore
from ghstars.core.tagging import (
    StarArchivedError,
    StarListMembershipDriftError,
    StarNotFoundError,
    TagPushError,
    tag_star,
)


def test_tag_star_pushes_to_github_immediately_for_an_existing_list(
    tmp_path: Path, make_star: StarFactory
) -> None:
    star = make_star("example-owner/ghstars")
    lst = List(id="L_1", name="Explore: Tool", slug="explore-tool")
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([lst])
    client = FakeGitHubClient(stars=[star], lists=[lst])

    result = tag_star(client, store, "example-owner/ghstars", "Explore: Tool")

    assert result.star.list_ids == ["L_1"]
    assert result.star.pending_list_ids is None
    assert result.removed_list_ids == []
    saved = {s.full_name: s for s in store.load_stars()}
    assert saved["example-owner/ghstars"].list_ids == ["L_1"]
    # The fake client and List membership update immediately.
    assert client.fetch_stars()[0].list_ids == ["L_1"]
    assert "example-owner/ghstars" in client.fetch_lists()[0].items


def test_tag_star_creates_a_missing_list_for_real_and_pushes_immediately(
    tmp_path: Path, make_star: StarFactory
) -> None:
    star = make_star("example-owner/ghstars")
    store = StateStore(tmp_path)
    store.save_stars([star])
    client = FakeGitHubClient(stars=[star])

    result = tag_star(client, store, "example-owner/ghstars", "Explore: New")

    created = client.fetch_lists()
    assert len(created) == 1
    assert created[0].name == "Explore: New"
    assert created[0].is_private is False
    assert created[0].items == ["example-owner/ghstars"]
    assert result.star.list_ids == [created[0].id]
    saved_lists = store.load_lists()
    assert saved_lists[0].intent == "Explore"
    assert saved_lists[0].category == "New"


def test_tag_star_creates_a_private_list_when_requested(
    tmp_path: Path, make_star: StarFactory
) -> None:
    star = make_star("example-owner/ghstars")
    store = StateStore(tmp_path)
    store.save_stars([star])
    client = FakeGitHubClient(stars=[star])

    tag_star(client, store, "example-owner/ghstars", "Explore: Secret", is_private=True)

    assert client.fetch_lists()[0].is_private is True


def test_tag_star_accumulates_across_two_immediate_calls(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Each call pushes immediately, so local `list_ids` is already live
    by the time a second `tag_star()` call reads it -- no drift, no
    staged edit to merge, unlike the old pending_list_ids model."""
    star = make_star("example-owner/ghstars")
    lists = [
        List(id="L_1", name="Explore: A", slug="a"),
        List(id="L_2", name="Explore: B", slug="b"),
    ]
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists(lists)
    client = FakeGitHubClient(stars=[star], lists=lists)

    tag_star(client, store, "example-owner/ghstars", "Explore: A")
    result = tag_star(client, store, "example-owner/ghstars", "Explore: B")

    assert sorted(result.star.list_ids) == ["L_1", "L_2"]


def test_tag_star_is_idempotent_when_already_tagged(
    tmp_path: Path, make_star: StarFactory
) -> None:
    star = make_star("example-owner/ghstars", list_ids=["L_1"])
    lst = List(id="L_1", name="Explore: A", slug="a", items=["example-owner/ghstars"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([lst])
    client = FakeGitHubClient(stars=[star], lists=[lst])

    result = tag_star(client, store, "example-owner/ghstars", "Explore: A")

    assert result.star.list_ids == ["L_1"]
    assert result.removed_list_ids == []


def test_tag_star_raises_when_star_not_found_locally(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    client = FakeGitHubClient()

    with pytest.raises(StarNotFoundError):
        tag_star(client, store, "example-owner/nonexistent", "Explore: Tool")


def test_tag_star_rejects_an_archived_star(
    tmp_path: Path, make_star: StarFactory
) -> None:
    star = make_star("example-owner/gone", archived=True)
    store = StateStore(tmp_path)
    store.save_stars([star])
    client = FakeGitHubClient()

    with pytest.raises(StarArchivedError):
        tag_star(client, store, "example-owner/gone", "Explore: Tool")


def test_tag_star_reuses_a_list_created_elsewhere_since_the_last_sync(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """The local lists.json cache can be stale (a List created on
    github.com/phone since the last `ghstars sync`) -- tag_star must
    check live GitHub state, not the stale cache, or it creates a
    duplicate List with no `ghstars` command able to clean it up."""
    star = make_star("example-owner/ghstars")
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([])  # stale: local cache doesn't know about it yet
    existing = List(id="L_1", name="Explore: Tool", slug="explore-tool")
    client = FakeGitHubClient(stars=[star], lists=[existing])

    result = tag_star(client, store, "example-owner/ghstars", "Explore: Tool")

    assert result.star.list_ids == ["L_1"]
    assert len(client.fetch_lists()) == 1  # no duplicate created


def test_tag_star_strips_a_sibling_intent_list_in_the_same_category(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Spec story 16/17: moving a Star from Current to Retired (same
    Category) is a single `tag` call -- the old lifecycle List is
    auto-removed, not left dangling alongside the new one."""
    current = List(
        id="L_current",
        name="Current: Tool",
        slug="current-tool",
        items=["example-owner/ghstars"],
    )
    retired = List(id="L_retired", name="Retired: Tool", slug="retired-tool")
    star = make_star("example-owner/ghstars", list_ids=["L_current"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([current, retired])
    client = FakeGitHubClient(stars=[star], lists=[current, retired])

    result = tag_star(client, store, "example-owner/ghstars", "Retired: Tool")

    assert result.star.list_ids == ["L_retired"]
    assert result.removed_list_ids == ["L_current"]


def test_tag_star_does_not_strip_across_different_categories(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Exclusivity is scoped to the same Category -- a lifecycle List
    for a different Category is untouched."""
    explore_a = List(
        id="L_a", name="Explore: A", slug="a", items=["example-owner/ghstars"]
    )
    current_b = List(id="L_b", name="Current: B", slug="b")
    star = make_star("example-owner/ghstars", list_ids=["L_a"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([explore_a, current_b])
    client = FakeGitHubClient(stars=[star], lists=[explore_a, current_b])

    result = tag_star(client, store, "example-owner/ghstars", "Current: B")

    assert sorted(result.star.list_ids) == ["L_a", "L_b"]
    assert result.removed_list_ids == []


def test_tag_star_does_not_strip_for_reference_intent(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Reference stands alone, no lifecycle (CONTEXT.md) -- tagging into
    a Reference List never strips an existing Explore/Current/Retired
    List, even in the same Category."""
    explore_tool = List(
        id="L_explore",
        name="Explore: Tool",
        slug="explore-tool",
        items=["example-owner/ghstars"],
    )
    reference_tool = List(id="L_ref", name="Reference: Tool", slug="ref-tool")
    star = make_star("example-owner/ghstars", list_ids=["L_explore"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([explore_tool, reference_tool])
    client = FakeGitHubClient(stars=[star], lists=[explore_tool, reference_tool])

    result = tag_star(client, store, "example-owner/ghstars", "Reference: Tool")

    assert sorted(result.star.list_ids) == ["L_explore", "L_ref"]
    assert result.removed_list_ids == []


def test_tag_star_does_not_strip_for_general_intent(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """An unprefixed General List (intent=None) never strips an
    existing lifecycle List, and is itself never a strip candidate."""
    current_tool = List(
        id="L_current",
        name="Current: Tool",
        slug="current-tool",
        items=["example-owner/ghstars"],
    )
    general = List(id="L_general", name="Vendored skills", slug="vendored-skills")
    star = make_star("example-owner/ghstars", list_ids=["L_current"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([current_tool, general])
    client = FakeGitHubClient(stars=[star], lists=[current_tool, general])

    result = tag_star(client, store, "example-owner/ghstars", "Vendored skills")

    assert sorted(result.star.list_ids) == ["L_current", "L_general"]
    assert result.removed_list_ids == []


def test_tag_star_blocks_and_names_diverged_lists_when_local_is_stale(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Local star.list_ids says L_old; GitHub's live List membership
    disagrees (moved to L_new since the last `ghstars sync`, e.g. via
    github.com). tag_star must not guess a resolution -- it names the
    diverged Lists and refuses to compute or push anything."""
    old_list = List(id="L_old", name="Explore: Old", slug="old")  # no longer a member
    new_list = List(
        id="L_new", name="Explore: New", slug="new", items=["example-owner/ghstars"]
    )
    star = make_star("example-owner/ghstars", list_ids=["L_old"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([old_list, new_list])
    client = FakeGitHubClient(stars=[star], lists=[old_list, new_list])

    with pytest.raises(StarListMembershipDriftError) as exc_info:
        tag_star(client, store, "example-owner/ghstars", "Explore: New")

    assert exc_info.value.full_name == "example-owner/ghstars"
    assert sorted(exc_info.value.diverged_list_names) == [
        "Explore: New",
        "Explore: Old",
    ]
    assert "Explore: New" in str(exc_info.value)
    assert "Explore: Old" in str(exc_info.value)

    # Nothing changed anywhere -- no push, no local write.
    saved = {s.full_name: s for s in store.load_stars()}
    assert saved["example-owner/ghstars"].list_ids == ["L_old"]
    assert client.fetch_stars()[0].list_ids == ["L_old"]  # unchanged, no push
    assert (
        "example-owner/ghstars" in client.fetch_lists()[1].items
    )  # L_new unchanged too


def test_tag_star_fails_outright_with_no_local_write_on_push_failure(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """A push failure for a non-conflict reason (network/API error, List
    deleted concurrently) fails the whole call -- no fallback staging,
    matching `unstar_cmd`'s remote-first, write-only-on-success pattern."""

    class _FailingClient(FakeGitHubClient):
        def update_list_membership_for_item(
            self, item_id: str, list_ids: list[str]
        ) -> None:
            raise RuntimeError("boom: simulated network failure")

    star = make_star("example-owner/ghstars")
    lst = List(id="L_1", name="Explore: Tool", slug="explore-tool")
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([lst])
    client = _FailingClient(stars=[star], lists=[lst])

    with pytest.raises(TagPushError) as exc_info:
        tag_star(client, store, "example-owner/ghstars", "Explore: Tool")

    assert exc_info.value.full_name == "example-owner/ghstars"
    saved = {s.full_name: s for s in store.load_stars()}
    assert saved["example-owner/ghstars"].list_ids == []
    assert saved["example-owner/ghstars"].pending_list_ids is None


def test_tag_star_pushes_via_a_pre_resolved_node_id_when_supplied(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """A bulk caller (the TUI) resolves node IDs in one batched call up
    front and threads the result in -- tag_star must use it instead of
    triggering its own per-item resolution."""

    class _NodeOnlyClient(FakeGitHubClient):
        def update_list_membership_for_item(
            self, item_id: str, list_ids: list[str]
        ) -> None:
            raise AssertionError(
                "must not resolve its own node ID when one was supplied"
            )

    star = make_star("example-owner/ghstars")
    lst = List(id="L_1", name="Explore: Tool", slug="explore-tool")
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([lst])
    client = _NodeOnlyClient(stars=[star], lists=[lst])

    result = tag_star(
        client,
        store,
        "example-owner/ghstars",
        "Explore: Tool",
        node_id="example-owner/ghstars",  # FakeGitHubClient's node IDs == full_name
    )

    assert result.star.list_ids == ["L_1"]
