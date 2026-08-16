from pathlib import Path

import pytest
from conftest import StarFactory

from ghstars.core.fake_client import FakeGitHubClient
from ghstars.core.models import List, RateLimitStatus
from ghstars.core.state_store import StateStore
from ghstars.core.sync import RateLimitExceededError, sync


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
