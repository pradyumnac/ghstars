"""Tests for `RealGitHubClient.resolve_repository_node_ids` (ticket 16):
resolving several repos' GitHub node IDs in one aliased GraphQL request
instead of one round trip per repo. Monkeypatches `_graphql`, the single
chokepoint every real call goes through -- no subprocess, no network,
same convention as test_paginate.py.
"""

import pytest

from ghstars.github import client as gh_client
from ghstars.github.client import RealGitHubClient


def test_resolve_repository_node_ids_makes_exactly_one_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def _fake(
        query: str, cursor: str | None = None, **variables: object
    ) -> dict[str, object]:
        calls.append(query)
        return {"r0": {"id": "R_a"}, "r1": {"id": "R_b"}}

    monkeypatch.setattr(gh_client, "_graphql", _fake)
    client = RealGitHubClient()

    result = client.resolve_repository_node_ids(["pradyumnac/a", "pradyumnac/b"])

    assert result == {"pradyumnac/a": "R_a", "pradyumnac/b": "R_b"}
    assert len(calls) == 1
    assert "r0: repository(owner:" in calls[0]
    assert "r1: repository(owner:" in calls[0]


def test_resolve_repository_node_ids_omits_a_repo_github_could_not_find(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake(
        query: str, cursor: str | None = None, **variables: object
    ) -> dict[str, object]:
        return {"r0": {"id": "R_a"}, "r1": None}

    monkeypatch.setattr(gh_client, "_graphql", _fake)
    client = RealGitHubClient()

    result = client.resolve_repository_node_ids(["pradyumnac/a", "pradyumnac/renamed"])

    assert result == {"pradyumnac/a": "R_a"}
    assert "pradyumnac/renamed" not in result


def test_resolve_repository_node_ids_of_an_empty_list_makes_no_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def _fake(
        query: str, cursor: str | None = None, **variables: object
    ) -> dict[str, object]:
        calls.append(query)
        return {}

    monkeypatch.setattr(gh_client, "_graphql", _fake)
    client = RealGitHubClient()

    result = client.resolve_repository_node_ids([])

    assert result == {}
    assert calls == []


def test_update_list_membership_for_node_skips_id_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def _fake(
        query: str, cursor: str | None = None, **variables: object
    ) -> dict[str, object]:
        calls.append(query)
        return {"updateUserListsForItem": {"item": {"__typename": "Repository"}}}

    monkeypatch.setattr(gh_client, "_graphql", _fake)
    client = RealGitHubClient()

    client.update_list_membership_for_node("R_a", ["L_1"])

    assert len(calls) == 1
    assert "repository(owner:" not in calls[0]  # no node-ID resolution call
    assert "updateUserListsForItem" in calls[0]
