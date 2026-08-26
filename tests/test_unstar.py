from pathlib import Path

from conftest import StarFactory

from ghstars.core.fake_client import FakeGitHubClient
from ghstars.core.models import List
from ghstars.core.state_store import StateStore
from ghstars.core.unstar import unstar_star


def test_unstar_star_removes_on_github_and_archives_locally(
    tmp_path: Path, make_star: StarFactory
) -> None:
    lst = List(id="L_1", name="Explore: Tool", slug="explore-tool")
    star = make_star("pradyumnac/ghstars", list_ids=["L_1"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([lst])
    lst_with_item = lst.model_copy(update={"items": ["pradyumnac/ghstars"]})
    client = FakeGitHubClient(stars=[star], lists=[lst_with_item])

    result = unstar_star(client, store, "pradyumnac/ghstars")

    assert result.full_name == "pradyumnac/ghstars"
    assert result.found_locally is True
    saved = {s.full_name: s for s in store.load_stars()}
    assert saved["pradyumnac/ghstars"].archived is True
    assert saved["pradyumnac/ghstars"].archived_at is not None
    assert saved["pradyumnac/ghstars"].list_ids == []
    # Every other field is retained, not deleted.
    assert saved["pradyumnac/ghstars"].description == star.description
    assert saved["pradyumnac/ghstars"].html_url == star.html_url
    # Removed from GitHub for real -- the fake client no longer has it.
    assert "pradyumnac/ghstars" not in {s.full_name for s in client.fetch_stars()}
    saved_lists = {lst.id: lst for lst in store.load_lists()}
    assert "pradyumnac/ghstars" not in saved_lists["L_1"].items


def test_unstar_star_when_no_local_record_still_unstars_on_github(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """A repo can be unstarred on GitHub even if the local snapshot
    never had it (e.g. starred and unstarred between syncs from
    another client) -- `found_locally` tells the caller which
    happened, not whether the GitHub-side mutation succeeded."""
    live_star = make_star("pradyumnac/ghost")
    store = StateStore(tmp_path)
    store.save_stars([])
    store.save_lists([])
    client = FakeGitHubClient(stars=[live_star])

    result = unstar_star(client, store, "pradyumnac/ghost")

    assert result.found_locally is False
    assert "pradyumnac/ghost" not in {s.full_name for s in client.fetch_stars()}
