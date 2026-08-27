from datetime import UTC, datetime

from ghstars.core.fields import FIELD_REGISTRY, select_fields
from ghstars.core.models import List, RetriageEntry, Star


def _now() -> datetime:
    return datetime(2026, 8, 16, tzinfo=UTC)


def _star() -> Star:
    return Star(
        full_name="example-owner/ghstars",
        html_url="https://github.com/example-owner/ghstars",
        description="Classify GitHub stars",
        starred_at=_now(),
        first_seen=_now(),
        last_checked=_now(),
        language="Python",
        stargazer_count=3,
    )


def test_registry_has_all_four_record_types() -> None:
    assert set(FIELD_REGISTRY) == {"star", "list", "retriage", "export"}


def test_star_basic_matches_prior_default_star_fields() -> None:
    assert FIELD_REGISTRY["star"].basic == (
        "full_name",
        "language",
        "stargazer_count",
    )


def test_list_basic_matches_prior_default_lists_fields() -> None:
    assert FIELD_REGISTRY["list"].basic == (
        "name",
        "intent",
        "category",
        "is_private",
        "malformed",
    )


def test_retriage_basic_matches_prior_default_retriage_fields() -> None:
    assert FIELD_REGISTRY["retriage"].basic == (
        "star_full_name",
        "attempted_list_ids",
        "conflict_detected_at",
        "resolved",
    )


def test_export_basic_matches_prior_default_export_fields() -> None:
    assert FIELD_REGISTRY["export"].basic == ("full_name", "html_url", "description")


def test_star_and_export_detailed_sets_cover_every_star_field() -> None:
    assert set(FIELD_REGISTRY["star"].detailed) == set(Star.model_fields)
    assert set(FIELD_REGISTRY["export"].detailed) == set(Star.model_fields)


def test_list_detailed_set_covers_every_list_field() -> None:
    assert set(FIELD_REGISTRY["list"].detailed) == set(List.model_fields)


def test_retriage_detailed_set_covers_every_retriage_field() -> None:
    assert set(FIELD_REGISTRY["retriage"].detailed) == set(RetriageEntry.model_fields)


def test_star_and_export_basic_sets_disagree() -> None:
    # `ghstars list`'s default and export's default have always shown
    # different fields; the registry keeps them as separate entries rather
    # than collapsing them into one Star-keyed default.
    assert FIELD_REGISTRY["star"].basic != FIELD_REGISTRY["export"].basic


def test_select_fields_restricts_and_reorders() -> None:
    star = _star()
    result = select_fields(star, ["stargazer_count", "full_name"])
    assert list(result.keys()) == ["stargazer_count", "full_name"]
    assert result == {
        "stargazer_count": 3,
        "full_name": "example-owner/ghstars",
    }


def test_select_fields_none_dumps_every_field_in_declared_order() -> None:
    star = _star()
    result = select_fields(star, None)
    assert list(result.keys()) == list(Star.model_fields.keys())


def test_select_fields_json_safe_output() -> None:
    star = _star()
    result = select_fields(star, ["starred_at"])
    assert result == {"starred_at": "2026-08-16T00:00:00Z"}
