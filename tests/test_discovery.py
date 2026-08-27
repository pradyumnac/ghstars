"""Tests for `ghstars.core.discovery` (ticket 31 Scope A + the Archived
default/opt-in half of Scope B): the one Filter/Sort/search query shared
by the TUI and (later) the CLI.
"""

from datetime import UTC, datetime, timedelta

from conftest import StarFactory

from ghstars.core.discovery import (
    OLDER_THAN_CUTOFF,
    RECENCY_CUTOFFS,
    StarRow,
    available_facets,
    query_stars,
)
from ghstars.core.models import List

NOW = datetime(2026, 8, 16, tzinfo=UTC)


def _names(rows: list[StarRow]) -> list[str]:
    return [row.star.full_name for row in rows]


# -- Filters ------------------------------------------------------------------


def test_filter_category(make_star: StarFactory) -> None:
    explore = List(
        id="L1", name="Explore: AI", slug="explore-ai", category="AI", intent="Explore"
    )
    other = List(id="L2", name="Current: Tools", slug="current-tools", category="Tools")
    a = make_star("owner/a", list_ids=["L1"])
    b = make_star("owner/b", list_ids=["L2"])
    rows = query_stars([a, b], [explore, other], filters=["category:AI"])
    assert _names(rows) == ["owner/a"]


def test_filter_intent(make_star: StarFactory) -> None:
    explore = List(id="L1", name="Explore: AI", slug="explore-ai", intent="Explore")
    current = List(
        id="L2", name="Current: Tools", slug="current-tools", intent="Current"
    )
    a = make_star("owner/a", list_ids=["L1"])
    b = make_star("owner/b", list_ids=["L2"])
    rows = query_stars([a, b], [explore, current], filters=["intent:Current"])
    assert _names(rows) == ["owner/b"]


def test_filter_list(make_star: StarFactory) -> None:
    lst = List(id="L1", name="Explore: AI", slug="explore-ai")
    a = make_star("owner/a", list_ids=["L1"])
    b = make_star("owner/b", list_ids=[])
    rows = query_stars([a, b], [lst], filters=["list:L1"])
    assert _names(rows) == ["owner/a"]


def test_filter_language(make_star: StarFactory) -> None:
    a = make_star("owner/a", language="Python")
    b = make_star("owner/b", language="Go")
    rows = query_stars([a, b], [], filters=["language:Go"])
    assert _names(rows) == ["owner/b"]


def test_filter_license(make_star: StarFactory) -> None:
    a = make_star("owner/a", license="MIT")
    b = make_star("owner/b", license="Apache-2.0")
    rows = query_stars([a, b], [], filters=["license:MIT"])
    assert _names(rows) == ["owner/a"]


def test_filter_owner(make_star: StarFactory) -> None:
    a = make_star("alice/tool")
    b = make_star("bob/tool")
    rows = query_stars([a, b], [], filters=["owner:alice"])
    assert _names(rows) == ["alice/tool"]


def test_filter_forks(make_star: StarFactory) -> None:
    a = make_star("owner/a", fork=True)
    b = make_star("owner/b", fork=False)
    rows = query_stars([a, b], [], filters=["forks"])
    assert _names(rows) == ["owner/a"]


def test_filter_followed(make_star: StarFactory) -> None:
    a = make_star("owner/a", follow=True)
    b = make_star("owner/b", follow=False)
    rows = query_stars([a, b], [], filters=["followed"])
    assert _names(rows) == ["owner/a"]


def test_filter_unclassified(make_star: StarFactory) -> None:
    a = make_star("owner/a", list_ids=["L1"])
    b = make_star("owner/b", list_ids=[])
    rows = query_stars([a, b], [], filters=["unclassified"])
    assert _names(rows) == ["owner/b"]


def test_filter_recency_windows(make_star: StarFactory) -> None:
    now = datetime.now(UTC)
    for key, window in RECENCY_CUTOFFS.items():
        inside = make_star(
            "owner/inside", starred_at=now - window + timedelta(minutes=1)
        )
        outside = make_star(
            "owner/outside", starred_at=now - window - timedelta(minutes=1)
        )
        rows = query_stars([inside, outside], [], filters=[f"recent:{key}"])
        assert _names(rows) == ["owner/inside"], key


def test_filter_recency_older_than_1y(make_star: StarFactory) -> None:
    now = datetime.now(UTC)
    old = make_star("owner/old", starred_at=now - OLDER_THAN_CUTOFF - timedelta(days=1))
    recent = make_star("owner/recent", starred_at=now - timedelta(days=1))
    rows = query_stars([old, recent], [], filters=["recent:older_1y"])
    assert _names(rows) == ["owner/old"]


def test_filters_and_combine(make_star: StarFactory) -> None:
    """Two Filters combine with AND, not OR."""
    a = make_star("alice/py", language="Python", fork=True)
    b = make_star("alice/go", language="Go", fork=True)
    c = make_star("bob/py", language="Python", fork=False)
    rows = query_stars([a, b, c], [], filters=["owner:alice", "language:Python"])
    assert _names(rows) == ["alice/py"]


# -- Search ---------------------------------------------------------------


def test_search_matches_name_and_description(make_star: StarFactory) -> None:
    named = make_star("owner/needle", description="A useful widget")
    described = make_star("owner/other", description="Contains the needle")
    unrelated = make_star("owner/nope", description="Nothing here")
    rows = query_stars([named, described, unrelated], [], search="needle")
    assert set(_names(rows)) == {"owner/needle", "owner/other"}


def test_search_is_case_insensitive(make_star: StarFactory) -> None:
    star = make_star("owner/Needle")
    rows = query_stars([star], [], search="NEEDLE")
    assert _names(rows) == ["owner/Needle"]


# -- Sort -------------------------------------------------------------------


def test_sort_name_both_directions(make_star: StarFactory) -> None:
    a = make_star("owner/alpha")
    b = make_star("owner/bravo")
    assert _names(query_stars([b, a], [], sort="name_asc")) == [
        "owner/alpha",
        "owner/bravo",
    ]
    assert _names(query_stars([b, a], [], sort="name_desc")) == [
        "owner/bravo",
        "owner/alpha",
    ]


def test_sort_starred_both_directions(make_star: StarFactory) -> None:
    older = make_star("owner/older", starred_at=NOW - timedelta(days=10))
    newer = make_star("owner/newer", starred_at=NOW)
    assert _names(query_stars([older, newer], [], sort="starred_desc")) == [
        "owner/newer",
        "owner/older",
    ]
    assert _names(query_stars([older, newer], [], sort="starred_asc")) == [
        "owner/older",
        "owner/newer",
    ]


def test_sort_stargazer_both_directions(make_star: StarFactory) -> None:
    low = make_star("owner/low", stargazer_count=5)
    high = make_star("owner/high", stargazer_count=500)
    assert _names(query_stars([low, high], [], sort="stargazer_desc")) == [
        "owner/high",
        "owner/low",
    ]
    assert _names(query_stars([low, high], [], sort="stargazer_asc")) == [
        "owner/low",
        "owner/high",
    ]


def test_sort_language_both_directions(make_star: StarFactory) -> None:
    ada = make_star("owner/ada", language="Ada")
    zig = make_star("owner/zig", language="Zig")
    assert _names(query_stars([zig, ada], [], sort="language_asc")) == [
        "owner/ada",
        "owner/zig",
    ]
    assert _names(query_stars([zig, ada], [], sort="language_desc")) == [
        "owner/zig",
        "owner/ada",
    ]


def test_sort_list_count_both_directions(make_star: StarFactory) -> None:
    lst = List(id="L1", name="Explore: Tool", slug="explore-tool")
    few = make_star("owner/few", list_ids=[])
    many = make_star("owner/many", list_ids=["L1"])
    assert _names(query_stars([few, many], [lst], sort="list_count_desc")) == [
        "owner/many",
        "owner/few",
    ]
    assert _names(query_stars([few, many], [lst], sort="list_count_asc")) == [
        "owner/few",
        "owner/many",
    ]


def test_sort_list_name_ascending_no_lists_last(make_star: StarFactory) -> None:
    list_a = List(id="LA", name="Explore: Alpha", slug="explore-alpha")
    list_b = List(id="LB", name="Explore: Bravo", slug="explore-bravo")
    in_b = make_star("owner/in-b", list_ids=["LB"])
    in_a = make_star("owner/in-a", list_ids=["LA"])
    unclassified = make_star("owner/none", list_ids=[])
    rows = query_stars(
        [in_b, in_a, unclassified], [list_a, list_b], sort="list_name_asc"
    )
    assert _names(rows) == ["owner/in-a", "owner/in-b", "owner/none"]


# -- Limit / offset determinism --------------------------------------------


def test_limit_and_offset_are_deterministic(make_star: StarFactory) -> None:
    stars = [
        make_star(f"owner/star-{i}", starred_at=NOW - timedelta(days=i))
        for i in range(5)
    ]
    first = query_stars(stars, [], sort="name_asc", limit=2, offset=1)
    second = query_stars(stars, [], sort="name_asc", limit=2, offset=1)
    assert _names(first) == _names(second)
    assert _names(first) == ["owner/star-1", "owner/star-2"]


# -- Archived default vs opt-in --------------------------------------------


def test_archived_excluded_by_default(make_star: StarFactory) -> None:
    active = make_star("owner/active", archived=False)
    archived = make_star("owner/archived", archived=True)
    rows = query_stars([active, archived], [])
    assert _names(rows) == ["owner/active"]


def test_archived_included_when_opted_in(make_star: StarFactory) -> None:
    active = make_star("owner/active", archived=False)
    archived = make_star("owner/archived", archived=True)
    rows = query_stars([active, archived], [], include_archived=True)
    assert set(_names(rows)) == {"owner/active", "owner/archived"}


# -- Facet enumeration ------------------------------------------------------


def test_available_facets(make_star: StarFactory) -> None:
    explore = List(
        id="L1", name="Explore: AI", slug="explore-ai", category="AI", intent="Explore"
    )
    current = List(
        id="L2",
        name="Current: Tools",
        slug="current-tools",
        category="Tools",
        intent="Current",
    )
    a = make_star("alice/a", language="Python", license="MIT", list_ids=["L1"])
    b = make_star("bob/b", language="Go", license="Apache-2.0", list_ids=["L2"])
    facets = available_facets([a, b], [explore, current])
    assert facets.categories == ["AI", "Tools"]
    assert facets.intents == ["Current", "Explore"]
    assert [lst.id for lst in facets.lists] == ["L2", "L1"]  # sorted by name
    assert facets.languages == ["Go", "Python"]
    assert facets.licenses == ["Apache-2.0", "MIT"]
    assert facets.owners == ["alice", "bob"]
