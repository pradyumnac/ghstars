from pathlib import Path

from conftest import StarFactory

from ghstars.core.fake_client import FakeGitHubClient
from ghstars.core.models import List
from ghstars.core.state_store import StateStore
from ghstars.core.unstar import bulk_unstar_stars, unstar_star


def test_unstar_star_removes_on_github_and_archives_locally(
    tmp_path: Path, make_star: StarFactory
) -> None:
    lst = List(id="L_1", name="Explore: Tool", slug="explore-tool")
    star = make_star("example-owner/ghstars", list_ids=["L_1"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([lst])
    lst_with_item = lst.model_copy(update={"items": ["example-owner/ghstars"]})
    client = FakeGitHubClient(stars=[star], lists=[lst_with_item])

    result = unstar_star(client, store, "example-owner/ghstars")

    assert result.full_name == "example-owner/ghstars"
    assert result.found_locally is True
    saved = {s.full_name: s for s in store.load_stars()}
    assert saved["example-owner/ghstars"].archived is True
    assert saved["example-owner/ghstars"].archived_at is not None
    assert saved["example-owner/ghstars"].list_ids == []
    # Every other field is retained, not deleted.
    assert saved["example-owner/ghstars"].description == star.description
    assert saved["example-owner/ghstars"].html_url == star.html_url
    # Removed from GitHub for real -- the fake client no longer has it.
    assert "example-owner/ghstars" not in {s.full_name for s in client.fetch_stars()}
    saved_lists = {lst.id: lst for lst in store.load_lists()}
    assert "example-owner/ghstars" not in saved_lists["L_1"].items


def test_unstar_star_when_no_local_record_still_unstars_on_github(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """A repo can be unstarred on GitHub even if the local snapshot
    never had it (e.g. starred and unstarred between syncs from
    another client) -- `found_locally` tells the caller which
    happened, not whether the GitHub-side mutation succeeded."""
    live_star = make_star("example-owner/ghost")
    store = StateStore(tmp_path)
    store.save_stars([])
    store.save_lists([])
    client = FakeGitHubClient(stars=[live_star])

    result = unstar_star(client, store, "example-owner/ghost")

    assert result.found_locally is False
    assert "example-owner/ghost" not in {s.full_name for s in client.fetch_stars()}


def test_bulk_unstar_stars_unstars_every_target(
    tmp_path: Path, make_star: StarFactory
) -> None:
    star_a = make_star("example-owner/a")
    star_b = make_star("example-owner/b")
    store = StateStore(tmp_path)
    store.save_stars([star_a, star_b])
    store.save_lists([])
    client = FakeGitHubClient(stars=[star_a, star_b])

    outcomes = bulk_unstar_stars(client, store, ["example-owner/a", "example-owner/b"])

    assert [o.full_name for o in outcomes] == ["example-owner/a", "example-owner/b"]
    assert all(o.error is None and o.result is not None for o in outcomes)
    remaining = {s.full_name for s in client.fetch_stars()}
    assert "example-owner/a" not in remaining
    assert "example-owner/b" not in remaining
    saved = {s.full_name: s for s in store.load_stars()}
    assert saved["example-owner/a"].archived is True
    assert saved["example-owner/b"].archived is True


def test_bulk_unstar_stars_isolates_one_targets_failure_from_the_rest(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """A bad target (GitHub rejects the removeStar mutation) fails on its
    own -- the good targets still get unstarred and reported."""

    class _FailsOnClient(FakeGitHubClient):
        def remove_star(self, item_id: str) -> None:
            if item_id == "example-owner/bad":
                raise RuntimeError("boom: simulated API failure")
            super().remove_star(item_id)

    star_a = make_star("example-owner/a")
    star_bad = make_star("example-owner/bad")
    star_c = make_star("example-owner/c")
    store = StateStore(tmp_path)
    store.save_stars([star_a, star_bad, star_c])
    store.save_lists([])
    client = _FailsOnClient(stars=[star_a, star_bad, star_c])

    outcomes = bulk_unstar_stars(
        client, store, ["example-owner/a", "example-owner/bad", "example-owner/c"]
    )

    by_name = {o.full_name: o for o in outcomes}
    assert by_name["example-owner/a"].error is None
    assert by_name["example-owner/c"].error is None
    assert by_name["example-owner/bad"].result is None
    assert by_name["example-owner/bad"].error is not None
    saved = {s.full_name: s for s in store.load_stars()}
    assert saved["example-owner/a"].archived is True
    assert saved["example-owner/c"].archived is True
    # The failing target was never touched -- neither locally...
    assert saved["example-owner/bad"].archived is False
    # ...nor on GitHub (still present in the fake client).
    assert "example-owner/bad" in {s.full_name for s in client.fetch_stars()}
