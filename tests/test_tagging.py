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

    updated = tag_star(client, store, "pradyumnac/ghstars", "Explore: Tool")

    assert updated.pending_list_ids == ["L_1"]
    assert updated.list_ids == []  # not pushed yet
    saved = {s.full_name: s for s in store.load_stars()}
    assert saved["pradyumnac/ghstars"].pending_list_ids == ["L_1"]


def test_tag_star_creates_a_missing_list_for_real_and_defaults_public(
    tmp_path: Path, make_star: StarFactory
) -> None:
    star = make_star("pradyumnac/ghstars")
    store = StateStore(tmp_path)
    store.save_stars([star])
    client = FakeGitHubClient(stars=[star])

    updated = tag_star(client, store, "pradyumnac/ghstars", "Explore: New")

    created = client.fetch_lists()
    assert len(created) == 1
    assert created[0].name == "Explore: New"
    assert created[0].is_private is False
    assert updated.pending_list_ids == [created[0].id]
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

    updated = tag_star(client, store, "pradyumnac/ghstars", "Explore: B")

    assert sorted(updated.pending_list_ids or []) == ["L_1", "L_2"]


def test_tag_star_is_idempotent_when_already_tagged(
    tmp_path: Path, make_star: StarFactory
) -> None:
    star = make_star("pradyumnac/ghstars", list_ids=["L_1"])
    lst = List(id="L_1", name="Explore: A", slug="a")
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([lst])
    client = FakeGitHubClient(stars=[star], lists=[lst])

    updated = tag_star(client, store, "pradyumnac/ghstars", "Explore: A")

    assert updated.pending_list_ids == ["L_1"]


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

    updated = tag_star(client, store, "pradyumnac/ghstars", "Explore: Tool")

    assert updated.pending_list_ids == ["L_1"]
    assert len(client.fetch_lists()) == 1  # no duplicate created
