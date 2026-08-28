"""Tests for `ghstars facets` (ticket 30 Scope 1, Decision 25)."""

import json
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


def test_facets_json_reports_every_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    tools = List(
        id="L_1",
        name="Explore: Tools",
        slug="explore-tools",
        intent="Explore",
        category="Tools",
    )
    store.save_lists([tools])
    store.save_stars(
        [make_star("owner/repo", language="Python", license="MIT", list_ids=["L_1"])]
    )
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["facets", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["categories"] == ["Tools"]
    assert payload["intents"] == ["Explore"]
    assert payload["languages"] == ["Python"]
    assert payload["licenses"] == ["MIT"]
    assert payload["owners"] == ["owner"]
    assert payload["lists"] == [tools.model_dump(mode="json")]


def test_facets_json_is_empty_groups_with_no_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path)
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["facets", "--json"])

    assert json.loads(result.output) == {
        "categories": [],
        "intents": [],
        "lists": [],
        "languages": [],
        "licenses": [],
        "owners": [],
    }


def test_facets_text_mode_prints_readable_groups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    store.save_stars([make_star("owner/repo", language="Python")])
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["facets"])

    assert result.exit_code == 0
    assert "Languages: Python" in result.output
    assert "Owners: owner" in result.output
