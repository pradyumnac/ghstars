"""Mechanical enforcement of ADR 0003 (GitHub sync is always explicit,
never auto-triggered) -- docs/adr/0003-github-sync-is-always-explicit.md.

A bare `ghstars tui` launch (`on_mount`, no user interaction) may only
ever make one real GitHub call: `GitHubClient.check_rate_limit()`, ADR
0003's explicit read-only-metadata exception. Every other GitHub read
(`fetch_stars`, `fetch_lists`, ...) must stay local-state-only until the
user takes an explicit action. This test spies on
`ghstars.github.client._graphql`, the single chokepoint every real call
goes through, so a future layer that accidentally adds an auto-fetch on
mount fails this test instead of only a manual review catching it (ADR
0003's own "Consequences" section). `spy_on_graphql` (graphql_spy.py) is
written to be reusable for a future ticket 14 (agent skill) test making
the same assertion.
"""

from pathlib import Path

import pytest
from graphql_spy import spy_on_graphql

from ghstars.core.state_store import StateStore
from ghstars.github.client import _RATE_LIMIT_QUERY, RealGitHubClient
from ghstars.tui.app import TuiApp


async def test_tui_bare_launch_calls_graphql_only_for_the_rate_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path)
    client = RealGitHubClient()
    calls = spy_on_graphql(monkeypatch)

    app = TuiApp(client=client, store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()

    # Exactly the rate-limit check, exactly once -- no fetch_stars(),
    # fetch_lists(), or anything else, from mount alone.
    assert calls == [_RATE_LIMIT_QUERY]
