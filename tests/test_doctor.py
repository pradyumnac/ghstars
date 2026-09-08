"""Tests for `ghstars doctor` (ADR 0005)."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import ghstars.cli as cli_module
from ghstars.cli import app
from ghstars.core.doctor import bootstrap_lists, diagnose, planned_creates
from ghstars.core.fake_client import FakeGitHubClient
from ghstars.core.models import List
from ghstars.core.state_store import StateStore

runner = CliRunner()

VOCAB = ["Tool", "Library", "General"]


def _use(
    monkeypatch: pytest.MonkeyPatch, store: StateStore, client: FakeGitHubClient
) -> None:
    """Write a real `[taxonomy]` table, so the CLI tests do not silently fall
    through to the shipped default vocabulary.
    """
    store.base_dir.mkdir(parents=True, exist_ok=True)
    config_path = store.base_dir / "ghstars.toml"
    config_path.write_text(f"[taxonomy]\ncategories = {json.dumps(VOCAB)}\n")

    monkeypatch.setattr(cli_module, "get_store", lambda: store)
    monkeypatch.setattr(cli_module, "get_client", lambda: client)
    monkeypatch.setattr(cli_module, "ensure_config_dir", lambda: store.base_dir)
    monkeypatch.setattr(cli_module, "get_core_config_path", lambda: config_path)


def _list(list_id: str, name: str) -> List:
    return List(id=list_id, name=name, slug=name.lower().replace(" ", "-"))


def test_diagnose_flags_a_malformed_name() -> None:
    report = diagnose([_list("L1", "Exploring: Foo")], categories=VOCAB)

    assert report.problems[0].problem == "malformed"
    assert report.create_blocked is True


def test_diagnose_offers_both_repairs_for_an_unblessed_category() -> None:
    """ghstars never picks between them; only the user knows which is right."""
    report = diagnose([_list("L1", "Explore: Wombat")], categories=VOCAB)

    assert report.problems[0].problem == "unblessed"
    assert len(report.problems[0].repairs) == 2


def test_diagnose_normalizes_before_checking_the_vocabulary() -> None:
    report = diagnose([_list("L1", "Explore:  Tool")], categories=VOCAB)

    assert report.problems == []


def test_diagnose_reports_blessed_categories_with_no_list() -> None:
    report = diagnose([_list("L1", "Explore: Tool")], categories=VOCAB)

    assert report.missing_categories == ["General", "Library"]
    assert report.ok is False


def test_diagnose_is_ok_when_every_category_has_a_list() -> None:
    lists = [
        _list("L1", "Explore: Tool"),
        _list("L2", "Explore: Library"),
        _list("L3", "Explore: General"),
    ]

    report = diagnose(lists, categories=VOCAB)

    assert report.ok is True
    assert report.create_blocked is False


def test_planned_creates_uses_the_given_intent() -> None:
    report = diagnose([_list("L1", "Explore: Tool")], categories=VOCAB)

    assert planned_creates(report, intent="Learn") == [
        "Learn: General",
        "Learn: Library",
    ]


def test_bootstrap_lists_creates_one_per_missing_category() -> None:
    client = FakeGitHubClient(lists=[_list("L1", "Explore: Tool")])
    report = diagnose(client.fetch_lists(), categories=VOCAB)

    created = bootstrap_lists(client, report, intent="Explore")

    assert created == ["Explore: General", "Explore: Library"]
    assert len(client.fetch_lists()) == 3


def test_doctor_reports_without_touching_github(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = FakeGitHubClient(lists=[_list("L1", "Explore: Wombat")])
    _use(monkeypatch, StateStore(tmp_path), client)

    result = runner.invoke(app, ["doctor"])

    assert "Wombat" in result.output
    assert len(client.fetch_lists()) == 1


def test_doctor_fix_requires_yes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = FakeGitHubClient(lists=[_list("L1", "Explore: Tool")])
    _use(monkeypatch, StateStore(tmp_path), client)

    result = runner.invoke(app, ["doctor", "--fix", "--intent", "Explore"])

    assert result.exit_code != 0
    assert len(client.fetch_lists()) == 1


def test_doctor_fix_requires_an_explicit_intent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ghstars never guesses an Intent (ticket 03)."""
    client = FakeGitHubClient(lists=[_list("L1", "Explore: Tool")])
    _use(monkeypatch, StateStore(tmp_path), client)

    result = runner.invoke(app, ["doctor", "--fix", "--yes"])

    assert result.exit_code != 0
    assert len(client.fetch_lists()) == 1


def test_doctor_fix_is_blocked_by_a_name_needing_attention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rename can turn an unblessed Category blessed, so names come first."""
    client = FakeGitHubClient(lists=[_list("L1", "Explore: Wombat")])
    _use(monkeypatch, StateStore(tmp_path), client)

    result = runner.invoke(
        app, ["doctor", "--fix", "--yes", "--intent", "Explore"]
    )

    assert result.exit_code != 0
    assert len(client.fetch_lists()) == 1


def test_doctor_force_overrides_the_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = FakeGitHubClient(lists=[_list("L1", "Explore: Wombat")])
    _use(monkeypatch, StateStore(tmp_path), client)

    runner.invoke(
        app, ["doctor", "--fix", "--yes", "--intent", "Explore", "--force"]
    )

    names = sorted(lst.name for lst in client.fetch_lists())
    assert names == [
        "Explore: General",
        "Explore: Library",
        "Explore: Tool",
        "Explore: Wombat",
    ]


def test_doctor_json_carries_the_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The skill layer reads this, so the shape is the contract."""
    client = FakeGitHubClient(lists=[_list("L1", "Explore: Wombat")])
    _use(monkeypatch, StateStore(tmp_path), client)

    result = runner.invoke(app, ["doctor", "--json"])
    payload = json.loads(result.output)

    assert payload["ok"] is False
    assert payload["create_blocked"] is True
    assert payload["problems"][0]["list_name"] == "Explore: Wombat"
    assert payload["created"] == []
