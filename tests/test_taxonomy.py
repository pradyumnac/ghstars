import pytest

from ghstars.core.models import Intent, List
from ghstars.core.taxonomy import (
    classify_list,
    parse_list_name,
    strip_lifecycle_siblings,
)


@pytest.mark.parametrize(
    ("name", "intent", "category"),
    [
        ("Explore: Tool", "Explore", "Tool"),
        ("Current: Dev Tooling", "Current", "Dev Tooling"),
        ("Retired: Editors", "Retired", "Editors"),
        ("Reference: AI Agents", "Reference", "AI Agents"),
        ("Explore: General", "Explore", "General"),
    ],
)
def test_parse_list_name_recognizes_intent_prefixes(
    name: str, intent: Intent, category: str
) -> None:
    parsed = parse_list_name(name)
    assert parsed.intent == intent
    assert parsed.category == category
    assert parsed.malformed is False


@pytest.mark.parametrize(
    "name",
    [
        "Vendored skills",
        "AI Agents Reference",
        "Explorer",
        "My Tools",
        "Explore",  # bare Intent word, no separator attempt -> General
        "Explore Zone",  # normal word boundary, not a separator attempt
        "Current Events",
    ],
)
def test_parse_list_name_recognizes_unprefixed_general(name: str) -> None:
    parsed = parse_list_name(name)
    assert parsed.intent is None
    assert parsed.category is None
    assert parsed.malformed is False


@pytest.mark.parametrize(
    "name",
    [
        "explore: Foo",  # wrong case
        "Explore - Foo",  # wrong separator
        "Explore-Foo",  # wrong separator, no space
        "Exploring: Foo",  # unrecognized word before the colon
        "current: bar",  # wrong case
    ],
)
def test_parse_list_name_flags_malformed_never_guesses(name: str) -> None:
    parsed = parse_list_name(name)
    assert parsed.malformed is True
    assert parsed.intent is None
    assert parsed.category is None


def test_classify_list_sets_intent_and_category_from_name() -> None:
    lst = List(id="L_1", name="Explore: Tool", slug="explore-tool")

    classified = classify_list(lst)

    assert classified.intent == "Explore"
    assert classified.category == "Tool"
    assert classified.malformed is False
    # original untouched (model_copy)
    assert lst.intent is None


def test_classify_list_flags_malformed_and_leaves_intent_category_none() -> None:
    lst = List(id="L_1", name="Exploring: Foo", slug="exploring-foo")

    classified = classify_list(lst)

    assert classified.intent is None
    assert classified.category is None
    assert classified.malformed is True


def test_classify_list_general_is_not_malformed() -> None:
    lst = List(id="L_1", name="Vendored skills", slug="vendored-skills")

    classified = classify_list(lst)

    assert classified.intent is None
    assert classified.category is None
    assert classified.malformed is False


def test_strip_lifecycle_siblings_removes_a_same_category_different_intent_id() -> None:
    current = List(
        id="L_current",
        name="Current: Tool",
        slug="current-tool",
        intent="Current",
        category="Tool",
    )
    retired = List(
        id="L_retired",
        name="Retired: Tool",
        slug="retired-tool",
        intent="Retired",
        category="Tool",
    )

    new_ids, removed = strip_lifecycle_siblings(
        ["L_current"], lists=[current, retired], target=retired
    )

    assert new_ids == []
    assert removed == ["L_current"]


def test_strip_lifecycle_siblings_leaves_different_category_ids_alone() -> None:
    explore_a = List(
        id="L_a", name="Explore: A", slug="a", intent="Explore", category="A"
    )
    current_b = List(
        id="L_b", name="Current: B", slug="b", intent="Current", category="B"
    )

    new_ids, removed = strip_lifecycle_siblings(
        ["L_a"], lists=[explore_a, current_b], target=current_b
    )

    assert sorted(new_ids) == ["L_a"]
    assert removed == []


def test_strip_lifecycle_siblings_exempts_reference_targets() -> None:
    explore_tool = List(
        id="L_explore",
        name="Explore: Tool",
        slug="explore-tool",
        intent="Explore",
        category="Tool",
    )
    reference_tool = List(
        id="L_ref",
        name="Reference: Tool",
        slug="ref-tool",
        intent="Reference",
        category="Tool",
    )

    new_ids, removed = strip_lifecycle_siblings(
        ["L_explore"], lists=[explore_tool, reference_tool], target=reference_tool
    )

    assert new_ids == ["L_explore"]
    assert removed == []


def test_strip_lifecycle_siblings_exempts_general_ids_from_stripping() -> None:
    current_tool = List(
        id="L_current",
        name="Current: Tool",
        slug="current-tool",
        intent="Current",
        category="Tool",
    )
    general = List(id="L_general", name="Vendored skills", slug="vendored-skills")

    new_ids, removed = strip_lifecycle_siblings(
        ["L_general"], lists=[current_tool, general], target=current_tool
    )

    assert new_ids == ["L_general"]
    assert removed == []


def test_strip_lifecycle_siblings_is_a_no_op_when_no_sibling_present() -> None:
    retired = List(
        id="L_retired",
        name="Retired: Tool",
        slug="retired-tool",
        intent="Retired",
        category="Tool",
    )

    new_ids, removed = strip_lifecycle_siblings([], lists=[retired], target=retired)

    assert new_ids == []
    assert removed == []
