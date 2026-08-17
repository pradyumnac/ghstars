from pathlib import Path

import pytest
from conftest import StarFactory

from ghstars.core.fake_client import FakeGitHubClient
from ghstars.core.models import List
from ghstars.core.state_store import StateStore
from ghstars.core.tagging import StarArchivedError, StarNotFoundError, tag_star


def test_tag_star_stages_pending_list_ids_for_an_existing_list(
    tmp_path: Path, make_star: StarFactory
) -> None:
    star = make_star("pradyumnac/ghstars")
    lst = List(id="L_1", name="Explore: Tool", slug="explore-tool")
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([lst])
    client = FakeGitHubClient(stars=[star], lists=[lst])

    result = tag_star(client, store, "pradyumnac/ghstars", "Explore: Tool")

    assert result.star.pending_list_ids == ["L_1"]
    assert result.star.list_ids == []  # not pushed yet
    assert result.removed_list_ids == []
    saved = {s.full_name: s for s in store.load_stars()}
    assert saved["pradyumnac/ghstars"].pending_list_ids == ["L_1"]


def test_tag_star_creates_a_missing_list_for_real_and_defaults_public(
    tmp_path: Path, make_star: StarFactory
) -> None:
    star = make_star("pradyumnac/ghstars")
    store = StateStore(tmp_path)
    store.save_stars([star])
    client = FakeGitHubClient(stars=[star])

    result = tag_star(client, store, "pradyumnac/ghstars", "Explore: New")

    created = client.fetch_lists()
    assert len(created) == 1
    assert created[0].name == "Explore: New"
    assert created[0].is_private is False
    assert result.star.pending_list_ids == [created[0].id]
    saved_lists = store.load_lists()
    assert saved_lists[0].intent == "Explore"
    assert saved_lists[0].category == "New"


def test_tag_star_creates_a_private_list_when_requested(
    tmp_path: Path, make_star: StarFactory
) -> None:
    star = make_star("pradyumnac/ghstars")
    store = StateStore(tmp_path)
    store.save_stars([star])
    client = FakeGitHubClient(stars=[star])

    tag_star(client, store, "pradyumnac/ghstars", "Explore: Secret", is_private=True)

    assert client.fetch_lists()[0].is_private is True


def test_tag_star_appends_to_an_existing_pending_edit(
    tmp_path: Path, make_star: StarFactory
) -> None:
    star = make_star("pradyumnac/ghstars", pending_list_ids=["L_1"])
    lists = [
        List(id="L_1", name="Explore: A", slug="a"),
        List(id="L_2", name="Explore: B", slug="b"),
    ]
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists(lists)
    client = FakeGitHubClient(stars=[star], lists=lists)

    result = tag_star(client, store, "pradyumnac/ghstars", "Explore: B")

    assert sorted(result.star.pending_list_ids or []) == ["L_1", "L_2"]


def test_tag_star_is_idempotent_when_already_tagged(
    tmp_path: Path, make_star: StarFactory
) -> None:
    star = make_star("pradyumnac/ghstars", list_ids=["L_1"])
    lst = List(id="L_1", name="Explore: A", slug="a")
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([lst])
    client = FakeGitHubClient(stars=[star], lists=[lst])

    result = tag_star(client, store, "pradyumnac/ghstars", "Explore: A")

    assert result.star.pending_list_ids == ["L_1"]
    assert result.removed_list_ids == []


def test_tag_star_raises_when_star_not_found_locally(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    client = FakeGitHubClient()

    with pytest.raises(StarNotFoundError):
        tag_star(client, store, "pradyumnac/nonexistent", "Explore: Tool")


def test_tag_star_rejects_an_archived_star(
    tmp_path: Path, make_star: StarFactory
) -> None:
    star = make_star("pradyumnac/gone", archived=True)
    store = StateStore(tmp_path)
    store.save_stars([star])
    client = FakeGitHubClient()

    with pytest.raises(StarArchivedError):
        tag_star(client, store, "pradyumnac/gone", "Explore: Tool")


def test_tag_star_reuses_a_list_created_elsewhere_since_the_last_sync(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """The local lists.json cache can be stale (a List created on
    github.com/phone since the last `ghstars sync`) -- tag_star must
    check live GitHub state, not the stale cache, or it creates a
    duplicate List with no `ghstars` command able to clean it up."""
    star = make_star("pradyumnac/ghstars")
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([])  # stale: local cache doesn't know about it yet
    existing = List(id="L_1", name="Explore: Tool", slug="explore-tool")
    client = FakeGitHubClient(stars=[star], lists=[existing])

    result = tag_star(client, store, "pradyumnac/ghstars", "Explore: Tool")

    assert result.star.pending_list_ids == ["L_1"]
    assert len(client.fetch_lists()) == 1  # no duplicate created


def test_tag_star_strips_a_sibling_intent_list_in_the_same_category(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Spec story 16/17: moving a Star from Current to Retired (same
    Category) is a single `tag` call -- the old lifecycle List is
    auto-removed, not left dangling alongside the new one."""
    current = List(id="L_current", name="Current: Tool", slug="current-tool")
    retired = List(id="L_retired", name="Retired: Tool", slug="retired-tool")
    star = make_star("pradyumnac/ghstars", list_ids=["L_current"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([current, retired])
    client = FakeGitHubClient(stars=[star], lists=[current, retired])

    result = tag_star(client, store, "pradyumnac/ghstars", "Retired: Tool")

    assert result.star.pending_list_ids == ["L_retired"]
    assert result.removed_list_ids == ["L_current"]


def test_tag_star_does_not_strip_across_different_categories(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Exclusivity is scoped to the same Category -- a lifecycle List
    for a different Category is untouched."""
    explore_a = List(id="L_a", name="Explore: A", slug="a")
    current_b = List(id="L_b", name="Current: B", slug="b")
    star = make_star("pradyumnac/ghstars", list_ids=["L_a"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([explore_a, current_b])
    client = FakeGitHubClient(stars=[star], lists=[explore_a, current_b])

    result = tag_star(client, store, "pradyumnac/ghstars", "Current: B")

    assert sorted(result.star.pending_list_ids or []) == ["L_a", "L_b"]
    assert result.removed_list_ids == []


def test_tag_star_does_not_strip_for_reference_intent(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Reference stands alone, no lifecycle (CONTEXT.md) -- tagging into
    a Reference List never strips an existing Explore/Current/Retired
    List, even in the same Category."""
    explore_tool = List(id="L_explore", name="Explore: Tool", slug="explore-tool")
    reference_tool = List(id="L_ref", name="Reference: Tool", slug="ref-tool")
    star = make_star("pradyumnac/ghstars", list_ids=["L_explore"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([explore_tool, reference_tool])
    client = FakeGitHubClient(stars=[star], lists=[explore_tool, reference_tool])

    result = tag_star(client, store, "pradyumnac/ghstars", "Reference: Tool")

    assert sorted(result.star.pending_list_ids or []) == ["L_explore", "L_ref"]
    assert result.removed_list_ids == []


def test_tag_star_does_not_strip_for_general_intent(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """An unprefixed General List (intent=None) never strips an
    existing lifecycle List, and is itself never a strip candidate."""
    current_tool = List(id="L_current", name="Current: Tool", slug="current-tool")
    general = List(id="L_general", name="Vendored skills", slug="vendored-skills")
    star = make_star("pradyumnac/ghstars", list_ids=["L_current"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([current_tool, general])
    client = FakeGitHubClient(stars=[star], lists=[current_tool, general])

    result = tag_star(client, store, "pradyumnac/ghstars", "Vendored skills")

    assert sorted(result.star.pending_list_ids or []) == ["L_current", "L_general"]
    assert result.removed_list_ids == []
