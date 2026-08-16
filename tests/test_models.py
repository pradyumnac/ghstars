from datetime import UTC, datetime

from ghstars.core.models import List, Nudge, RetriageEntry, Star


def _now() -> datetime:
    return datetime(2026, 8, 16, tzinfo=UTC)


def test_star_requires_no_optional_fields_beyond_defaults() -> None:
    star = Star(
        full_name="pradyumnac/ghstars",
        html_url="https://github.com/pradyumnac/ghstars",
        starred_at=_now(),
        first_seen=_now(),
        last_checked=_now(),
    )
    assert star.description is None
    assert star.language is None
    assert star.stargazer_count == 0
    assert star.fork is False
    assert star.follow is False
    assert star.archived is False
    assert star.archived_at is None
    assert star.list_ids == []


def test_star_carries_full_field_set() -> None:
    star = Star(
        full_name="pradyumnac/ghstars",
        html_url="https://github.com/pradyumnac/ghstars",
        description="Classify GitHub stars",
        starred_at=_now(),
        first_seen=_now(),
        language="Python",
        stargazer_count=3,
        fork=True,
        follow=True,
        archived=True,
        archived_at=_now(),
        last_checked=_now(),
        list_ids=["L_1"],
    )
    assert star.stargazer_count == 3
    assert star.fork is True
    assert star.list_ids == ["L_1"]


def test_list_intent_and_category() -> None:
    lst = List(
        id="L_1",
        name="Explore: Vendored Skills",
        slug="explore-vendored-skills",
        is_private=False,
        intent="Explore",
        category="Vendored Skills",
    )
    assert lst.intent == "Explore"
    assert lst.category == "Vendored Skills"
    assert lst.items == []


def test_list_general_has_no_intent() -> None:
    lst = List(id="L_2", name="Cooking", slug="cooking", is_private=True)
    assert lst.intent is None
    assert lst.category is None


def test_retriage_entry_defaults_unresolved() -> None:
    entry = RetriageEntry(
        star_full_name="pradyumnac/ghstars",
        attempted_list_ids=["L_1"],
        conflict_detected_at=_now(),
    )
    assert entry.resolved is False


def test_nudge_defaults() -> None:
    nudge = Nudge(slug="tag-friction", theme="tagging", message="Bulk tag is slow")
    assert nudge.count == 1
