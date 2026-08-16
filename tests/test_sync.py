from pathlib import Path

import pytest
from conftest import StarFactory

from ghstars.core.fake_client import FakeGitHubClient
from ghstars.core.models import List, RateLimitStatus
from ghstars.core.state_store import StateStore
from ghstars.core.sync import RateLimitExceededError, remove_star_from_lists, sync


def test_sync_fetches_and_persists_stars(
    tmp_path: Path, make_star: StarFactory
) -> None:
    star = make_star()
    client = FakeGitHubClient(stars=[star])
    store = StateStore(tmp_path)

    result = sync(client, store)

    assert result.star_count == 1
    assert store.load_stars() == [star]


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
    assert store.load_stars() == [star]


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
