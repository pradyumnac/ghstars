from pathlib import Path

import pytest
from conftest import StarFactory

from ghstars.core.fake_client import FakeGitHubClient
from ghstars.core.models import RateLimitStatus
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
