"""Tests for `ghstars tag`/`unstar`'s explicit bulk actions and unstar's
mandatory `--yes` confirmation (ticket 30 Scope 4).
"""

import json
from pathlib import Path

import pytest
from conftest import StarFactory
from typer.testing import CliRunner

import ghstars.cli as cli_module
from ghstars.cli import app
from ghstars.core.fake_client import FakeGitHubClient
from ghstars.core.state_store import StateStore

runner = CliRunner()


def _use_store(monkeypatch: pytest.MonkeyPatch, store: StateStore) -> None:
    monkeypatch.setattr(cli_module, "get_store", lambda: store)
    monkeypatch.setattr(cli_module, "ensure_config_dir", lambda: store.base_dir)


def _use_client(monkeypatch: pytest.MonkeyPatch, client: FakeGitHubClient) -> None:
    monkeypatch.setattr(cli_module, "get_client", lambda: client)


# -- unstar: mandatory --yes ---------------------------------------------


def test_unstar_without_yes_fails_and_never_mutates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    star = make_star("example-owner/x")
    store = StateStore(tmp_path)
    store.save_stars([star])
    _use_store(monkeypatch, store)
    client = FakeGitHubClient(stars=[star])
    _use_client(monkeypatch, client)

    result = runner.invoke(app, ["unstar", "example-owner/x"])

    assert result.exit_code == 1
    assert "example-owner/x" in {s.full_name for s in client.fetch_stars()}
    assert store.load_stars()[0].archived is False


def test_unstar_without_yes_json_reports_invalid_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    star = make_star("example-owner/x")
    store = StateStore(tmp_path)
    store.save_stars([star])
    _use_store(monkeypatch, store)
    _use_client(monkeypatch, FakeGitHubClient(stars=[star]))

    result = runner.invoke(app, ["unstar", "example-owner/x", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["error"]["code"] == "invalid_input"


def test_unstar_with_yes_mutates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    star = make_star("example-owner/x")
    store = StateStore(tmp_path)
    store.save_stars([star])
    _use_store(monkeypatch, store)
    client = FakeGitHubClient(stars=[star])
    _use_client(monkeypatch, client)

    result = runner.invoke(app, ["unstar", "example-owner/x", "--yes"])

    assert result.exit_code == 0
    assert store.load_stars()[0].archived is True


# -- unstar: bulk ---------------------------------------------------------


def test_unstar_bulk_prints_targets_before_mutating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    star_a = make_star("example-owner/a")
    star_b = make_star("example-owner/b")
    store = StateStore(tmp_path)
    store.save_stars([star_a, star_b])
    _use_store(monkeypatch, store)
    _use_client(monkeypatch, FakeGitHubClient(stars=[star_a, star_b]))

    result = runner.invoke(
        app, ["unstar", "example-owner/a", "--repo", "example-owner/b", "--yes"]
    )

    assert result.exit_code == 0
    assert "Targets: example-owner/a, example-owner/b" in result.output


def test_unstar_bulk_without_yes_never_mutates_any_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    star_a = make_star("example-owner/a")
    star_b = make_star("example-owner/b")
    store = StateStore(tmp_path)
    store.save_stars([star_a, star_b])
    _use_store(monkeypatch, store)
    client = FakeGitHubClient(stars=[star_a, star_b])
    _use_client(monkeypatch, client)

    result = runner.invoke(
        app, ["unstar", "example-owner/a", "--repo", "example-owner/b"]
    )

    assert result.exit_code == 1
    assert {s.full_name for s in client.fetch_stars()} == {
        "example-owner/a",
        "example-owner/b",
    }


def test_unstar_bulk_json_reports_success_and_failure_per_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    class _FailsOnBad(FakeGitHubClient):
        def remove_star(self, item_id: str) -> None:
            if item_id == "example-owner/bad":
                raise RuntimeError("boom")
            super().remove_star(item_id)

    star_a = make_star("example-owner/a")
    star_bad = make_star("example-owner/bad")
    store = StateStore(tmp_path)
    store.save_stars([star_a, star_bad])
    _use_store(monkeypatch, store)
    _use_client(monkeypatch, _FailsOnBad(stars=[star_a, star_bad]))

    result = runner.invoke(
        app,
        ["unstar", "example-owner/a", "--repo", "example-owner/bad", "--yes", "--json"],
    )

    assert result.exit_code == 4  # EXIT_PARTIAL
    payload = json.loads(result.stdout)
    by_name = {row["full_name"]: row for row in payload["results"]}
    assert by_name["example-owner/a"]["unstarred"] is True
    assert by_name["example-owner/bad"]["unstarred"] is False
    assert by_name["example-owner/bad"]["error"] is not None
    assert by_name["example-owner/bad"]["error_code"] == "unexpected_error"
    assert "Targets:" in result.stderr


def test_unstar_bulk_all_fail_exits_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    class _AlwaysFails(FakeGitHubClient):
        def remove_star(self, item_id: str) -> None:
            raise RuntimeError("boom")

    star_a = make_star("example-owner/a")
    star_b = make_star("example-owner/b")
    store = StateStore(tmp_path)
    store.save_stars([star_a, star_b])
    _use_store(monkeypatch, store)
    _use_client(monkeypatch, _AlwaysFails(stars=[star_a, star_b]))

    result = runner.invoke(
        app, ["unstar", "example-owner/a", "--repo", "example-owner/b", "--yes"]
    )

    assert result.exit_code == 1  # EXIT_TERMINAL


# -- tag: single-target behavior is unchanged ------------------------------


def test_tag_single_target_unchanged_json_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    star = make_star("example-owner/x")
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([])
    _use_store(monkeypatch, store)
    _use_client(monkeypatch, FakeGitHubClient(stars=[star], lists=[]))

    result = runner.invoke(app, ["tag", "example-owner/x", "Explore: Tool", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert set(payload) == {"full_name", "list_ids", "removed_list_ids"}


# -- tag: bulk --------------------------------------------------------------


def test_tag_bulk_tags_every_target_into_the_same_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    star_a = make_star("example-owner/a")
    star_b = make_star("example-owner/b")
    store = StateStore(tmp_path)
    store.save_stars([star_a, star_b])
    store.save_lists([])
    _use_store(monkeypatch, store)
    _use_client(monkeypatch, FakeGitHubClient(stars=[star_a, star_b], lists=[]))

    result = runner.invoke(
        app,
        [
            "tag",
            "example-owner/a",
            "Explore: Tool",
            "--repo",
            "example-owner/b",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    by_name = {row["full_name"]: row for row in payload["results"]}
    assert by_name["example-owner/a"]["tagged"] is True
    assert by_name["example-owner/b"]["tagged"] is True
    for row in by_name.values():
        assert len(row["list_ids"]) == 1


def test_tag_bulk_isolates_one_targets_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    star_a = make_star("example-owner/a")
    store = StateStore(tmp_path)
    store.save_stars([star_a])
    store.save_lists([])
    _use_store(monkeypatch, store)
    _use_client(monkeypatch, FakeGitHubClient(stars=[star_a], lists=[]))

    result = runner.invoke(
        app,
        [
            "tag",
            "example-owner/a",
            "Explore: Tool",
            "--repo",
            "example-owner/missing",
            "--json",
        ],
    )

    assert result.exit_code == 4  # EXIT_PARTIAL
    payload = json.loads(result.output)
    by_name = {row["full_name"]: row for row in payload["results"]}
    assert by_name["example-owner/a"]["tagged"] is True
    assert by_name["example-owner/missing"]["tagged"] is False
    assert by_name["example-owner/missing"]["error"] is not None
    assert by_name["example-owner/missing"]["error_code"] == "no_local_record"
