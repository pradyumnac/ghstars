from datetime import UTC, datetime
from typing import Protocol

import pytest

from ghstars.core.models import Star

NOW = datetime(2026, 8, 16, tzinfo=UTC)


class StarFactory(Protocol):
    def __call__(self, full_name: str = ..., **overrides: object) -> Star: ...


@pytest.fixture(autouse=True)
def _no_ghstars_home_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let a real `GHSTARS_HOME` in the test runner's shell leak in.

    `ghstars.cli.deps.get_ghstars_home()` reads this environment variable
    (ticket 30); tests that want the default path must see it unset.
    """
    monkeypatch.delenv("GHSTARS_HOME", raising=False)


@pytest.fixture
def make_star() -> StarFactory:
    def _make(full_name: str = "example-owner/ghstars", **overrides: object) -> Star:
        defaults = {
            "full_name": full_name,
            "html_url": f"https://github.com/{full_name}",
            "starred_at": NOW,
            "first_seen": NOW,
            "last_checked": NOW,
        }
        return Star.model_validate(defaults | overrides)

    return _make
