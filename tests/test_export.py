import csv
import io
import json
from pathlib import Path

import pytest
import yaml
from conftest import StarFactory

from ghstars.core.export import (
    DEFAULT_EXPORT_FIELDS,
    ExportConfig,
    ExportEntry,
    run_export,
    select_stars,
)
from ghstars.core.models import Intent, List


def _list(
    name: str,
    *,
    id: str = "L_1",
    intent: Intent | None = None,
    category: str | None = None,
    malformed: bool = False,
    items: list[str] | None = None,
) -> List:
    return List(
        id=id,
        name=name,
        slug=name.lower().replace(" ", "-").replace(":", ""),
        intent=intent,
        category=category,
        malformed=malformed,
        items=items or [],
    )


# Config *loading* moved to `ghstars.core.config.load_core_config`
# (ticket 32 -- export config now lives under the `[export]` table of
# `ghstars.toml`, not its own `export.toml`). Those tests live in
# `tests/test_core_config.py`. `ExportConfig`/`ExportEntry` (the schema)
# and everything downstream of an already-loaded config stay here,
# unchanged.


# --- select_stars --------------------------------------------------------


def test_select_stars_matches_by_exact_list_name(make_star: StarFactory) -> None:
    lst = _list(
        "Current: Vendored Skills",
        id="L_cur",
        intent="Current",
        category="Vendored Skills",
        items=["a/one", "b/two"],
    )
    other = _list(
        "Explore: Other",
        id="L_other",
        intent="Explore",
        category="Other",
        items=["c/three"],
    )
    # Membership resolves through `Star.list_ids` now (see `select_stars`),
    # not `List.items` -- both are set here since `sync()` keeps them
    # reconciled in practice.
    stars = [
        make_star("a/one", list_ids=["L_cur"]),
        make_star("b/two", list_ids=["L_cur"]),
        make_star("c/three", list_ids=["L_other"]),
    ]
    entry = ExportEntry(
        name="tools",
        list_name="Current: Vendored Skills",
        output="tools.yaml",
        format="yaml",
    )

    selected, skipped = select_stars(entry, lists=[lst, other], stars=stars)

    assert [s.full_name for s in selected] == ["a/one", "b/two"]
    assert skipped == []


def test_select_stars_by_category_matches_across_intents_when_intent_omitted(
    make_star: StarFactory,
) -> None:
    explore = _list(
        "Explore: Vendored Skills",
        id="L_e",
        intent="Explore",
        category="Vendored Skills",
        items=["a/one"],
    )
    current = _list(
        "Current: Vendored Skills",
        id="L_c",
        intent="Current",
        category="Vendored Skills",
        items=["b/two"],
    )
    stars = [
        make_star("a/one", list_ids=["L_e"]),
        make_star("b/two", list_ids=["L_c"]),
    ]
    entry = ExportEntry(
        name="all", category="Vendored Skills", output="all.yaml", format="yaml"
    )

    selected, _ = select_stars(entry, lists=[explore, current], stars=stars)

    assert {s.full_name for s in selected} == {"a/one", "b/two"}


def test_select_stars_by_category_and_intent_answers_explore_not_yet_tried(
    make_star: StarFactory,
) -> None:
    explore = _list(
        "Explore: Vendored Skills",
        id="L_e",
        intent="Explore",
        category="Vendored Skills",
        items=["a/one"],
    )
    current = _list(
        "Current: Vendored Skills",
        id="L_c",
        intent="Current",
        category="Vendored Skills",
        items=["b/two"],
    )
    stars = [
        make_star("a/one", list_ids=["L_e"]),
        make_star("b/two", list_ids=["L_c"]),
    ]
    entry = ExportEntry(
        name="exploring",
        category="Vendored Skills",
        intent="Explore",
        output="exploring.yaml",
        format="yaml",
    )

    selected, _ = select_stars(entry, lists=[explore, current], stars=stars)

    assert [s.full_name for s in selected] == ["a/one"]


def test_select_stars_never_matches_a_malformed_list(make_star: StarFactory) -> None:
    malformed = _list("explore: Vendored Skills", malformed=True, items=["a/one"])
    stars = [make_star("a/one")]
    by_list = ExportEntry(
        name="x", list_name="explore: Vendored Skills", output="x.yaml", format="yaml"
    )
    by_category = ExportEntry(
        name="y", category="Vendored Skills", output="y.yaml", format="yaml"
    )

    selected_a, _ = select_stars(by_list, lists=[malformed], stars=stars)
    selected_b, _ = select_stars(by_category, lists=[malformed], stars=stars)

    assert selected_a == []
    assert selected_b == []


def test_select_stars_reports_a_related_malformed_list_as_skipped(
    make_star: StarFactory,
) -> None:
    malformed = _list("explore- Vendored Skills", malformed=True, items=["a/one"])
    stars = [make_star("a/one")]
    entry = ExportEntry(
        name="x", category="Vendored Skills", output="x.yaml", format="yaml"
    )

    selected, skipped = select_stars(entry, lists=[malformed], stars=stars)

    assert selected == []
    assert skipped == ["explore- Vendored Skills"]


def test_select_stars_does_not_report_an_unrelated_malformed_list(
    make_star: StarFactory,
) -> None:
    malformed = _list("current: Something Else", malformed=True, items=["a/one"])
    stars = [make_star("a/one")]
    entry = ExportEntry(
        name="x", category="Vendored Skills", output="x.yaml", format="yaml"
    )

    _, skipped = select_stars(entry, lists=[malformed], stars=stars)

    assert skipped == []


def test_select_stars_sorts_by_full_name(make_star: StarFactory) -> None:
    lst = _list(
        "Current: Tool",
        intent="Current",
        category="Tool",
        items=["z/last", "a/first"],
    )
    stars = [
        make_star("z/last", list_ids=["L_1"]),
        make_star("a/first", list_ids=["L_1"]),
    ]
    entry = ExportEntry(
        name="x", list_name="Current: Tool", output="x.yaml", format="yaml"
    )

    selected, _ = select_stars(entry, lists=[lst], stars=stars)

    assert [s.full_name for s in selected] == ["a/first", "z/last"]


def test_select_stars_resolves_membership_through_star_list_ids(
    make_star: StarFactory,
) -> None:
    """`List.items` and `Star.list_ids` are supposed to stay in sync via
    `sync()`'s `reconcile_list_membership` (see `core/sync.py`), but this
    fixture deliberately puts them out of sync to prove which one
    `select_stars` actually trusts. `Star.list_ids` must win: a Star
    listed in `List.items` but whose own `list_ids` disagrees is not
    selected, and a Star absent from `List.items` but carrying the
    List's id in `list_ids` is selected.
    """
    lst = _list(
        "Current: Tool",
        id="L_cur",
        intent="Current",
        category="Tool",
        items=["stale/only-in-items"],
    )
    stale_only_in_items = make_star("stale/only-in-items", list_ids=[])
    fresh_only_in_list_ids = make_star("fresh/only-in-list-ids", list_ids=["L_cur"])
    entry = ExportEntry(
        name="x", list_name="Current: Tool", output="x.yaml", format="yaml"
    )

    selected, _ = select_stars(
        entry,
        lists=[lst],
        stars=[stale_only_in_items, fresh_only_in_list_ids],
    )

    assert [s.full_name for s in selected] == ["fresh/only-in-list-ids"]


def test_select_stars_includes_archived_stars(make_star: StarFactory) -> None:
    """`select_stars` calls `query_stars(..., include_archived=True)`,
    preserving export's historical behavior of including Archived Stars --
    unlike the TUI/CLI discovery default, which excludes them. Guards
    against that keyword silently being dropped in a later refactor that
    tries to unify export's query call with the default one.
    """
    lst = _list(
        "Current: Tool", id="L_cur", intent="Current", category="Tool", items=[]
    )
    active = make_star("a/active", list_ids=["L_cur"], archived=False)
    archived = make_star("b/archived", list_ids=["L_cur"], archived=True)
    entry = ExportEntry(
        name="x", list_name="Current: Tool", output="x.yaml", format="yaml"
    )

    selected, _ = select_stars(entry, lists=[lst], stars=[active, archived])

    assert [s.full_name for s in selected] == ["a/active", "b/archived"]


# --- run_export ------------------------------------------------------------


def test_run_export_writes_yaml_with_default_fields(
    tmp_path: Path, make_star: StarFactory
) -> None:
    lst = _list("Current: Tool", intent="Current", category="Tool", items=["a/one"])
    star = make_star(
        "a/one",
        description="does a thing",
        html_url="https://x/a/one",
        list_ids=["L_1"],
    )
    config = ExportConfig(
        exports=[
            ExportEntry(
                name="tools",
                list_name="Current: Tool",
                output="tools.yaml",
                format="yaml",
            )
        ]
    )

    results = run_export(config, lists=[lst], stars=[star], base_dir=tmp_path)

    assert results[0].star_count == 1
    assert results[0].skipped_malformed_lists == []
    out_path = tmp_path / "tools.yaml"
    loaded = yaml.safe_load(out_path.read_text())
    assert loaded == [
        {
            "full_name": "a/one",
            "html_url": "https://x/a/one",
            "description": "does a thing",
        }
    ]
    assert list(loaded[0].keys()) == list(DEFAULT_EXPORT_FIELDS)


def test_run_export_writes_json(tmp_path: Path, make_star: StarFactory) -> None:
    lst = _list("Current: Tool", intent="Current", category="Tool", items=["a/one"])
    star = make_star("a/one", list_ids=["L_1"])
    config = ExportConfig(
        exports=[
            ExportEntry(
                name="tools",
                list_name="Current: Tool",
                output="tools.json",
                format="json",
            )
        ]
    )

    run_export(config, lists=[lst], stars=[star], base_dir=tmp_path)

    loaded = json.loads((tmp_path / "tools.json").read_text())
    assert loaded == [
        {"full_name": "a/one", "html_url": star.html_url, "description": None}
    ]


def test_run_export_writes_csv_with_custom_fields(
    tmp_path: Path, make_star: StarFactory
) -> None:
    lst = _list("Current: Tool", intent="Current", category="Tool", items=["a/one"])
    star = make_star("a/one", language="Python", stargazer_count=42, list_ids=["L_1"])
    config = ExportConfig(
        exports=[
            ExportEntry(
                name="tools",
                list_name="Current: Tool",
                output="tools.csv",
                format="csv",
                fields=["full_name", "language", "stargazer_count"],
            )
        ]
    )

    run_export(config, lists=[lst], stars=[star], base_dir=tmp_path)

    rows = list(csv.DictReader(io.StringIO((tmp_path / "tools.csv").read_text())))
    assert rows == [
        {"full_name": "a/one", "language": "Python", "stargazer_count": "42"}
    ]


def test_run_export_relative_output_resolves_against_base_dir(
    tmp_path: Path, make_star: StarFactory
) -> None:
    lst = _list("Current: Tool", intent="Current", category="Tool", items=["a/one"])
    star = make_star("a/one", list_ids=["L_1"])
    nested_base = tmp_path / "repo"
    nested_base.mkdir()
    config = ExportConfig(
        exports=[
            ExportEntry(
                name="tools",
                list_name="Current: Tool",
                output="nested/tools.yaml",
                format="yaml",
            )
        ]
    )

    results = run_export(config, lists=[lst], stars=[star], base_dir=nested_base)

    assert results[0].output == str(nested_base / "nested" / "tools.yaml")
    assert (nested_base / "nested" / "tools.yaml").exists()


def test_run_export_absolute_output_is_honored_as_is(
    tmp_path: Path, make_star: StarFactory
) -> None:
    lst = _list("Current: Tool", intent="Current", category="Tool", items=["a/one"])
    star = make_star("a/one", list_ids=["L_1"])
    absolute_target = tmp_path / "elsewhere" / "tools.yaml"
    config = ExportConfig(
        exports=[
            ExportEntry(
                name="tools",
                list_name="Current: Tool",
                output=str(absolute_target),
                format="yaml",
            )
        ]
    )

    results = run_export(
        config, lists=[lst], stars=[star], base_dir=tmp_path / "unrelated"
    )

    assert results[0].output == str(absolute_target)
    assert absolute_target.exists()


def test_run_export_expands_a_tilde_prefixed_output_to_the_home_dir(
    tmp_path: Path, make_star: StarFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    lst = _list("Current: Tool", intent="Current", category="Tool", items=["a/one"])
    star = make_star("a/one", list_ids=["L_1"])
    config = ExportConfig(
        exports=[
            ExportEntry(
                name="tools",
                list_name="Current: Tool",
                output="~/dotfiles/tools.yaml",
                format="yaml",
            )
        ]
    )

    results = run_export(
        config, lists=[lst], stars=[star], base_dir=tmp_path / "unrelated"
    )

    expected = fake_home / "dotfiles" / "tools.yaml"
    assert results[0].output == str(expected)
    assert expected.exists()
    # Never a literal "~" directory under base_dir.
    assert not (tmp_path / "unrelated" / "~").exists()


def test_run_export_leaves_no_temp_file_behind(
    tmp_path: Path, make_star: StarFactory
) -> None:
    lst = _list("Current: Tool", intent="Current", category="Tool", items=["a/one"])
    star = make_star("a/one", list_ids=["L_1"])
    config = ExportConfig(
        exports=[
            ExportEntry(
                name="tools",
                list_name="Current: Tool",
                output="tools.yaml",
                format="yaml",
            )
        ]
    )

    run_export(config, lists=[lst], stars=[star], base_dir=tmp_path)

    assert {p.name for p in tmp_path.iterdir()} == {"tools.yaml"}


def test_run_export_reports_skipped_malformed_lists_without_exporting_them(
    tmp_path: Path, make_star: StarFactory
) -> None:
    malformed = _list("explore- Tool", malformed=True, items=["a/one"])
    star = make_star("a/one")
    config = ExportConfig(
        exports=[
            ExportEntry(
                name="exploring",
                category="Tool",
                intent="Explore",
                output="exploring.yaml",
                format="yaml",
            )
        ]
    )

    results = run_export(config, lists=[malformed], stars=[star], base_dir=tmp_path)

    assert results[0].star_count == 0
    assert results[0].skipped_malformed_lists == ["explore- Tool"]
    assert yaml.safe_load((tmp_path / "exploring.yaml").read_text()) == []
