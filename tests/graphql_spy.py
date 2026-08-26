"""Reusable spy for `ghstars.github.client._graphql`, the single
chokepoint every real GitHub API call goes through (`GitHubClient`'s own
docstring; ADR 0003 --
docs/adr/0003-github-sync-is-always-explicit.md).

Lets a test mechanically assert a surface makes zero live GitHub calls
beyond an explicitly allowed few -- e.g. `ghstars tui`'s bare launch
calling only `check_rate_limit()` (see `test_no_auto_sync.py`) -- instead
of relying on manual review each time a new layer merges (ADR 0003's own
"Consequences" section calls this out by name). Written to be reusable
for a future ticket 14 (agent skill) test making the same assertion.
"""

import pytest

from ghstars.github import client as gh_client

# Return a rate-limit payload; tests validate calls separately from response shape.
_RATE_LIMIT_PAYLOAD: dict[str, object] = {
    "rateLimit": {"remaining": 5000, "limit": 5000}
}


def spy_on_graphql(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Patch `_graphql` for the caller's test; returns the list it
    appends each call's query text to, in call order. No subprocess, no
    network -- safe against the fake or the real `GitHubClient`.
    """
    calls: list[str] = []

    def _fake(
        query: str, cursor: str | None = None, **variables: object
    ) -> dict[str, object]:
        calls.append(query)
        return _RATE_LIMIT_PAYLOAD

    monkeypatch.setattr(gh_client, "_graphql", _fake)
    return calls
