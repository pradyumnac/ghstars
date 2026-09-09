"""Tests for `ghstars untag` (ADR 0005 follow-up: drop one List membership
without touching the rest, e.g. taking a Star out of the triage inbox).
"""

import json
from pathlib import Path

import pytest
from conftest import StarFactory
from typer.testing import CliRunner

import ghstars.cli as cli_module
from ghstars.cli import app
from ghstars.core.fake_client import FakeGitHubClient
from ghstars.core.models import List
from ghstars.core.state_store import StateStore

runner = CliRunner()


def _use(
    monkeypatch: pytest.MonkeyPatch, store: StateStore, client: FakeGitHubClient
) -> None:
    monkeypatch.setattr(cli_module, "get_store", lambda: store)
    monkeypatch.setattr(cli_module, "get_client", lambda: client)
    monkeypatch.setattr(cli_module, "ensure_config_dir", lambda: store.base_dir)


def test_untag_removes_only_the_named_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    inbox = List(id="L_inbox", name="Explore: General", slug="explore-general")
    tool = List(id="L_tool", name="Explore: Tool", slug="explore-tool")
    star = make_star("owner/repo", list_ids=["L_inbox", "L_tool"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    client = FakeGitHubClient(
        stars=[star],
        lists=[
            inbox.model_copy(update={"items": [star.full_name]}),
            tool.model_copy(update={"items": [star.full_name]}),
        ],
    )
    _use(monkeypatch, store, client)

    result = runner.invoke(app, ["untag", "owner/repo", "Explore: General"])

    assert result.exit_code == 0
    assert "Untagged owner/repo from 'Explore: General'" in result.output
    tool_list = next(lst for lst in client.fetch_lists() if lst.id == "L_tool")
    assert star.full_name in tool_list.items


def test_untag_json_reports_the_remaining_list_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    inbox = List(id="L_inbox", name="Explore: General", slug="explore-general")
    star = make_star("owner/repo", list_ids=["L_inbox"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    client = FakeGitHubClient(
        stars=[star], lists=[inbox.model_copy(update={"items": [star.full_name]})]
    )
    _use(monkeypatch, store, client)

    result = runner.invoke(
        app, ["untag", "owner/repo", "Explore: General", "--json"]
    )

    assert json.loads(result.output) == {"full_name": "owner/repo", "list_ids": []}


def test_untag_fails_when_star_not_in_that_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    star = make_star("owner/repo")
    store = StateStore(tmp_path)
    store.save_stars([star])
    client = FakeGitHubClient(stars=[star])
    _use(monkeypatch, store, client)

    result = runner.invoke(app, ["untag", "owner/repo", "Explore: Tool"])

    assert result.exit_code != 0
