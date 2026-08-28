"""Tests for `ghstars github-lists` output contract (ticket 30 Scope 2)."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import ghstars.cli as cli_module
from ghstars.cli import app
from ghstars.core.models import List
from ghstars.core.state_store import StateStore

runner = CliRunner()


def _use_store(monkeypatch: pytest.MonkeyPatch, store: StateStore) -> None:
    monkeypatch.setattr(cli_module, "get_store", lambda: store)
    monkeypatch.setattr(cli_module, "ensure_config_dir", lambda: store.base_dir)


def test_lists_json_envelope_has_no_cap_and_no_offset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path)
    tools = List(
        id="L_1", name="Explore: Tools", slug="explore-tools", category="Tools"
    )
    store.save_lists([tools])
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["github-lists", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "total": 1,
        "offset": 0,
        "limit": None,
        "rows": [
            {
                "name": "Explore: Tools",
                "intent": None,
                "category": "Tools",
                "is_private": False,
                "malformed": False,
            }
        ],
    }


def test_lists_details_flag_selects_the_detailed_field_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path)
    tools = List(
        id="L_1", name="Explore: Tools", slug="explore-tools", category="Tools"
    )
    store.save_lists([tools])
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["github-lists", "--json", "--details"])

    [row] = json.loads(result.output)["rows"]
    assert set(row) == set(List.model_fields)
