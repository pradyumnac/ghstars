"""Tests for `ghstars list`'s discovery surface (ticket 30 Scope 1).

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
from ghstars.core.models import List
from ghstars.core.state_store import StateStore

runner = CliRunner()


def _use_store(monkeypatch: pytest.MonkeyPatch, store: StateStore) -> None:
    monkeypatch.setattr(cli_module, "get_store", lambda: store)
    monkeypatch.setattr(cli_module, "ensure_config_dir", lambda: store.base_dir)


def test_list_json_returns_empty_array_with_no_stars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path)
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["list", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == []


def test_list_excludes_archived_stars_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    active = make_star("owner/active")
    archived = make_star("owner/archived", archived=True)
    store.save_stars([active, archived])
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["list", "--json", "--fields", "full_name"])

    assert json.loads(result.output) == [{"full_name": "owner/active"}]


def test_list_include_archived_adds_the_archived_field_to_default_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    active = make_star("owner/active")
    archived = make_star("owner/archived", archived=True)
    store.save_stars([active, archived])
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["list", "--json", "--include-archived"])

    rows = json.loads(result.output)
    full_names = {row["full_name"]: row["archived"] for row in rows}
    assert full_names == {"owner/active": False, "owner/archived": True}


def test_list_category_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    tools = List(id="L_1", name="Explore: Tools", slug="explore-tools", category="Tools")
    other = List(id="L_2", name="Explore: Other", slug="explore-other", category="Other")
    store.save_lists([tools, other])
    matching = make_star("owner/matching", list_ids=["L_1"])
    non_matching = make_star("owner/non-matching", list_ids=["L_2"])
    store.save_stars([matching, non_matching])
    _use_store(monkeypatch, store)

    result = runner.invoke(
        app, ["list", "--json", "--category", "Tools", "--fields", "full_name"]
    )

    assert json.loads(result.output) == [{"full_name": "owner/matching"}]


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
        ["list", "--json", "--language", "Python", "--fork", "--fields", "full_name"],
    )

    assert json.loads(result.output) == [{"full_name": "owner/both"}]


def test_list_search_matches_case_insensitive_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    store.save_stars([make_star("owner/GhStars"), make_star("owner/other")])
    _use_store(monkeypatch, store)

    result = runner.invoke(
        app, ["list", "--json", "--search", "ghstars", "--fields", "full_name"]
    )

    assert json.loads(result.output) == [{"full_name": "owner/GhStars"}]


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
        ["list", "--json", "--sort", "stargazer_desc", "--fields", "full_name"],
    )

    assert json.loads(result.output) == [
        {"full_name": "owner/high"},
        {"full_name": "owner/low"},
    ]


def test_list_unknown_sort_mode_fails_with_invalid_input_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path)
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["list", "--json", "--sort", "bogus"])

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
        app, ["list", "--json", "--recent", "1d", "--fields", "full_name"]
    )

    assert json.loads(result.output) == [{"full_name": "owner/recent"}]
