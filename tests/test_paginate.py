"""Tests for ghstars.github.client's `_paginate_all` cursor-walk logic.

Monkeypatches the module's `_graphql` (the only thing that shells out to
`gh`) with a canned in-memory sequence, so the pagination loop itself is
exercised with no network and no subprocess.
"""

import pytest

from ghstars.github import client as gh_client
from ghstars.github.schema import PageInfo


class _FakeGraphQL:
    """Canned page sequence, standing in for `_graphql`'s subprocess call."""

    def __init__(self, pages: list[dict[str, object]]) -> None:
        self._pages = pages
        self.calls: list[str | None] = []

    def __call__(
        self, query: str, cursor: str | None = None, **variables: str
    ) -> dict[str, object]:
        self.calls.append(cursor)
        return self._pages[len(self.calls) - 1]


def _parse_page(data: dict[str, object]) -> tuple[list[str], PageInfo]:
    items = data["items"]
    assert isinstance(items, list)
    page_info = data["page_info"]
    assert isinstance(page_info, PageInfo)
    return items, page_info


def test_paginate_all_walks_multiple_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    pages: list[dict[str, object]] = [
        {
            "items": ["a", "b"],
            "page_info": PageInfo(has_next_page=True, end_cursor="c1"),
        },
        {
            "items": ["c"],
            "page_info": PageInfo(has_next_page=False, end_cursor=None),
        },
    ]
    fake = _FakeGraphQL(pages)
    monkeypatch.setattr(gh_client, "_graphql", fake)

    result = list(gh_client._paginate_all("QUERY", _parse_page))

    assert result == ["a", "b", "c"]
    assert fake.calls == [None, "c1"]


def test_paginate_all_logs_debug_per_page(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    pages: list[dict[str, object]] = [
        {
            "items": ["a", "b"],
            "page_info": PageInfo(has_next_page=True, end_cursor="c1"),
        },
        {
            "items": ["c"],
            "page_info": PageInfo(has_next_page=False, end_cursor=None),
        },
    ]
    monkeypatch.setattr(gh_client, "_graphql", _FakeGraphQL(pages))

    with caplog.at_level("DEBUG", logger="ghstars.github"):
        list(gh_client._paginate_all("QUERY", _parse_page))

    messages = [r.message for r in caplog.records if r.name == "ghstars.github"]
    assert any("page=1 items=2" in m for m in messages)
    assert any("page=2 items=1" in m for m in messages)


def test_paginate_all_stops_on_single_page(monkeypatch: pytest.MonkeyPatch) -> None:
    pages: list[dict[str, object]] = [
        {
            "items": ["only"],
            "page_info": PageInfo(has_next_page=False, end_cursor=None),
        },
    ]
    fake = _FakeGraphQL(pages)
    monkeypatch.setattr(gh_client, "_graphql", fake)

    result = list(gh_client._paginate_all("QUERY", _parse_page))

    assert result == ["only"]
    assert fake.calls == [None]


def test_paginate_all_raises_on_null_cursor_with_more_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages: list[dict[str, object]] = [
        {
            "items": ["a"],
            "page_info": PageInfo(has_next_page=True, end_cursor=None),
        },
    ]
    fake = _FakeGraphQL(pages)
    monkeypatch.setattr(gh_client, "_graphql", fake)

    with pytest.raises(gh_client.GitHubApiError):
        list(gh_client._paginate_all("QUERY", _parse_page))
