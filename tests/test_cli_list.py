"""Tests for `ghstars stars`' discovery surface (ticket 30 Scope 1) and
output contract (ticket 30 Scope 2).

`list` is wired through `core.discovery.query_stars()` -- it implements no
Filter, Sort, or search logic of its own.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from conftest import StarFactory
from typer.testing import CliRunner

import ghstars.cli as cli_module
from ghstars.cli import app
from ghstars.cli.commands import list_lists
from ghstars.core.models import List
from ghstars.core.state_store import StateStore

runner = CliRunner()


def _use_store(monkeypatch: pytest.MonkeyPatch, store: StateStore) -> None:
    monkeypatch.setattr(cli_module, "get_store", lambda: store)
    monkeypatch.setattr(cli_module, "ensure_config_dir", lambda: store.base_dir)


def _rows(output: str) -> list[dict[str, object]]:
    payload = json.loads(output)
    rows: list[dict[str, object]] = payload["rows"]
    return rows


def test_list_json_envelope_is_empty_with_no_stars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path)
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["stars", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "total": 0,
        "offset": 0,
        "limit": 50,
        "rows": [],
    }


def test_list_excludes_archived_stars_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    active = make_star("owner/active")
    archived = make_star("owner/archived", archived=True)
    store.save_stars([active, archived])
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["stars", "--json", "--fields", "full_name"])

    assert _rows(result.output) == [{"full_name": "owner/active"}]


def test_list_include_archived_adds_the_archived_field_to_default_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    active = make_star("owner/active")
    archived = make_star("owner/archived", archived=True)
    store.save_stars([active, archived])
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["stars", "--json", "--include-archived"])

    full_names = {row["full_name"]: row["archived"] for row in _rows(result.output)}
    assert full_names == {"owner/active": False, "owner/archived": True}


def test_list_category_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    tools = List(
        id="L_1", name="Explore: Tools", slug="explore-tools", category="Tools"
    )
    other = List(
        id="L_2", name="Explore: Other", slug="explore-other", category="Other"
    )
    store.save_lists([tools, other])
    matching = make_star("owner/matching", list_ids=["L_1"])
    non_matching = make_star("owner/non-matching", list_ids=["L_2"])
    store.save_stars([matching, non_matching])
    _use_store(monkeypatch, store)

    result = runner.invoke(
        app, ["stars", "--json", "--category", "Tools", "--fields", "full_name"]
    )

    assert _rows(result.output) == [{"full_name": "owner/matching"}]


def test_list_two_filters_and_combine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    both = make_star("owner/both", language="Python", fork=True)
    only_language = make_star("owner/only-language", language="Python", fork=False)
    store.save_stars([both, only_language])
    _use_store(monkeypatch, store)

    result = runner.invoke(
        app,
        ["stars", "--json", "--language", "Python", "--fork", "--fields", "full_name"],
    )

    assert _rows(result.output) == [{"full_name": "owner/both"}]


@pytest.mark.parametrize(
    ("args", "expected_filter"),
    [
        (["--category", "Tools"], "category:Tools"),
        (["--intent", "Explore"], "intent:Explore"),
        (["--list", "L_1"], "list:L_1"),
        (["--language", "Python"], "language:Python"),
        (["--license", "MIT"], "license:MIT"),
        (["--owner", "owner"], "owner:owner"),
        (["--fork"], "forks"),
        (["--followed"], "followed"),
        (["--unclassified"], "unclassified"),
        (["--recent", "1d"], "recent:1d"),
    ],
)
def test_list_forwards_each_filter_to_core(
    args: list[str],
    expected_filter: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = StateStore(tmp_path)
    _use_store(monkeypatch, store)
    captured: dict[str, object] = {}

    def _query(*_args: object, **kwargs: object) -> list[object]:
        captured.update(kwargs)
        return []

    monkeypatch.setattr(list_lists, "query_stars", _query)
    result = runner.invoke(app, ["stars", "--json", *args])

    assert result.exit_code == 0
    assert captured["filters"] == [expected_filter]


def test_list_search_matches_case_insensitive_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    store.save_stars([make_star("owner/GhStars"), make_star("owner/other")])
    _use_store(monkeypatch, store)

    result = runner.invoke(
        app, ["stars", "--json", "--search", "ghstars", "--fields", "full_name"]
    )

    assert _rows(result.output) == [{"full_name": "owner/GhStars"}]


def test_list_sort_stargazer_desc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    store.save_stars(
        [
            make_star("owner/low", stargazer_count=1),
            make_star("owner/high", stargazer_count=100),
        ]
    )
    _use_store(monkeypatch, store)

    result = runner.invoke(
        app,
        ["stars", "--json", "--sort", "stargazer_desc", "--fields", "full_name"],
    )

    assert _rows(result.output) == [
        {"full_name": "owner/high"},
        {"full_name": "owner/low"},
    ]


def test_list_unknown_sort_mode_fails_with_invalid_input_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path)
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["stars", "--json", "--sort", "bogus"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["error"]["code"] == "invalid_input"


def test_list_recent_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    now = datetime.now(UTC)
    recent = make_star("owner/recent", starred_at=now - timedelta(hours=1))
    old = make_star("owner/old", starred_at=now - timedelta(days=400))
    store.save_stars([recent, old])
    _use_store(monkeypatch, store)

    result = runner.invoke(
        app, ["stars", "--json", "--recent", "1d", "--fields", "full_name"]
    )

    assert _rows(result.output) == [{"full_name": "owner/recent"}]


def test_list_default_basic_fields_are_full_name_list_names_starred_at_stargazers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    tools = List(id="L_1", name="Explore: Tools", slug="explore-tools")
    store.save_lists([tools])
    store.save_stars([make_star("owner/repo", list_ids=["L_1"])])
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["stars", "--json"])

    [row] = _rows(result.output)
    assert set(row) == {"full_name", "list_names", "starred_at", "stargazer_count"}
    assert row["list_names"] == ["Explore: Tools"]


def test_list_default_limit_is_50(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    store.save_stars([make_star(f"owner/repo-{i}") for i in range(60)])
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["stars", "--json"])

    payload = json.loads(result.output)
    assert payload == {"total": 60, "offset": 0, "limit": 50, "rows": payload["rows"]}
    assert len(payload["rows"]) == 50


def test_list_limit_overrides_the_default_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    store.save_stars([make_star(f"owner/repo-{i}") for i in range(10)])
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["stars", "--json", "--limit", "3"])

    payload = json.loads(result.output)
    assert payload["total"] == 10
    assert payload["limit"] == 3
    assert len(payload["rows"]) == 3


def test_list_offset_pages_past_already_seen_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    store.save_stars(
        [
            make_star("owner/a", starred_at=datetime(2026, 1, 1, tzinfo=UTC)),
            make_star("owner/b", starred_at=datetime(2026, 1, 2, tzinfo=UTC)),
            make_star("owner/c", starred_at=datetime(2026, 1, 3, tzinfo=UTC)),
        ]
    )
    _use_store(monkeypatch, store)

    first_page = runner.invoke(
        app, ["stars", "--json", "--limit", "2", "--fields", "full_name"]
    )
    second_page = runner.invoke(
        app,
        ["stars", "--json", "--limit", "2", "--offset", "2", "--fields", "full_name"],
    )

    assert _rows(first_page.output) == [
        {"full_name": "owner/c"},
        {"full_name": "owner/b"},
    ]
    assert _rows(second_page.output) == [{"full_name": "owner/a"}]


def test_list_details_flag_selects_the_detailed_field_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    store.save_stars([make_star("owner/repo")])
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["stars", "--json", "--details"])

    [row] = _rows(result.output)
    assert "list_names" in row
    assert "html_url" in row
    assert "archived" not in row


def test_list_archived_field_requires_include_archived(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    store.save_stars([make_star("owner/repo")])
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["stars", "--json", "--fields", "archived"])

    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "unknown_field"


def test_list_invalid_page_values_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path)
    _use_store(monkeypatch, store)

    for option, value in (("--limit", "0"), ("--limit", "-1"), ("--offset", "-1")):
        result = runner.invoke(app, ["stars", "--json", option, value])
        assert result.exit_code == 1
        assert json.loads(result.stderr)["error"]["code"] == "invalid_input"


def test_list_invalid_recent_window_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path)
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["stars", "--json", "--recent", "typo"])

    assert result.exit_code == 1
    assert json.loads(result.stderr)["error"]["code"] == "invalid_input"


def test_list_explicit_archived_field_requires_include_archived(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    store.save_stars([make_star("owner/repo")])
    _use_store(monkeypatch, store)

    result = runner.invoke(
        app, ["stars", "--json", "--include-archived", "--fields", "archived"]
    )

    assert result.exit_code == 0
    assert _rows(result.output) == [{"archived": False}]


def test_list_explicit_fields_overrides_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    store.save_stars([make_star("owner/repo")])
    _use_store(monkeypatch, store)

    result = runner.invoke(
        app, ["stars", "--json", "--details", "--fields", "full_name"]
    )

    assert _rows(result.output) == [{"full_name": "owner/repo"}]


def test_list_plain_text_prints_an_aligned_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    store.save_stars([make_star("owner/repo")])
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["stars", "--fields", "full_name,stargazer_count"])

    lines = result.output.splitlines()
    assert lines[0].split() == ["full_name", "stargazer_count"]
    assert lines[1].split() == ["owner/repo", "0"]


def test_list_details_plain_text_prints_key_value_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    store.save_stars([make_star("owner/repo")])
    _use_store(monkeypatch, store)

    result = runner.invoke(
        app, ["stars", "--details", "--fields", "full_name,language"]
    )

    assert result.output.splitlines() == [
        "full_name: owner/repo",
        "language: None",
    ]
