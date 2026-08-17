"""Tests for the `ghstars` CLI's `retriage` command (ticket 05).

Uses typer's own `CliRunner` -- no network, no real GitHub client. `main()`'s
`@app.callback()` calls `ensure_config_dir()`, which touches the real
`~/.ghstars/config` directory by default; every test here monkeypatches it
to a no-op alongside `get_store`, so nothing outside `tmp_path` is touched.
"""

import json
from pathlib import Path

import pytest
import yaml
from conftest import NOW, StarFactory
from typer.testing import CliRunner

import ghstars.cli as cli_module
from ghstars.cli import app
from ghstars.core.fake_client import FakeGitHubClient
from ghstars.core.models import List, RetriageEntry
from ghstars.core.state_store import StateStore

runner = CliRunner()


def _use_store(monkeypatch: pytest.MonkeyPatch, store: StateStore) -> None:
    monkeypatch.setattr(cli_module, "get_store", lambda: store)
    monkeypatch.setattr(cli_module, "ensure_config_dir", lambda: store.base_dir)


def _use_client(monkeypatch: pytest.MonkeyPatch, client: FakeGitHubClient) -> None:
    monkeypatch.setattr(cli_module, "get_client", lambda: client)


def _use_export_config(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    monkeypatch.setattr(cli_module, "get_export_config_path", lambda: path)


def test_retriage_json_lists_queue_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path)
    entry = RetriageEntry(
        star_full_name="pradyumnac/x",
        attempted_list_ids=["L_1"],
        conflict_detected_at=NOW,
    )
    store.save_retriage([entry])
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["retriage", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == [
        {
            "star_full_name": "pradyumnac/x",
            "attempted_list_ids": ["L_1"],
            "conflict_detected_at": "2026-08-16T00:00:00Z",
            "resolved": False,
        }
    ]


def test_retriage_json_is_an_empty_list_when_the_queue_is_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path)
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["retriage", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == []


def test_retriage_plain_text_reports_no_conflicts_when_the_queue_is_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path)
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["retriage"])

    assert result.exit_code == 0
    assert "No conflicts to retriage." in result.output


def test_tag_cmd_reports_removed_list_ids_in_plain_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    current = List(id="L_current", name="Current: Tool", slug="current-tool")
    retired = List(id="L_retired", name="Retired: Tool", slug="retired-tool")
    star = make_star("pradyumnac/ghstars", list_ids=["L_current"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([current, retired])
    _use_store(monkeypatch, store)
    _use_client(monkeypatch, FakeGitHubClient(stars=[star], lists=[current, retired]))

    result = runner.invoke(app, ["tag", "pradyumnac/ghstars", "Retired: Tool"])

    assert result.exit_code == 0
    assert "removed from 1 other List(s)" in result.output


def test_tag_cmd_reports_removed_list_ids_as_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    current = List(id="L_current", name="Current: Tool", slug="current-tool")
    retired = List(id="L_retired", name="Retired: Tool", slug="retired-tool")
    star = make_star("pradyumnac/ghstars", list_ids=["L_current"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([current, retired])
    _use_store(monkeypatch, store)
    _use_client(monkeypatch, FakeGitHubClient(stars=[star], lists=[current, retired]))

    result = runner.invoke(
        app, ["tag", "pradyumnac/ghstars", "Retired: Tool", "--json"]
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["removed_list_ids"] == ["L_current"]
    assert payload["pending_list_ids"] == ["L_retired"]


def test_tag_cmd_reports_no_removed_list_ids_when_nothing_stripped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    tool = List(id="L_tool", name="Explore: Tool", slug="explore-tool")
    star = make_star("pradyumnac/ghstars")
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([tool])
    _use_store(monkeypatch, store)
    _use_client(monkeypatch, FakeGitHubClient(stars=[star], lists=[tool]))

    result = runner.invoke(app, ["tag", "pradyumnac/ghstars", "Explore: Tool"])

    assert result.exit_code == 0
    assert "removed from" not in result.output


def test_export_cmd_reports_no_exports_configured_when_no_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path / "state")
    _use_store(monkeypatch, store)
    _use_export_config(monkeypatch, tmp_path / "export.toml")

    result = runner.invoke(app, ["export"])

    assert result.exit_code == 0
    assert "No exports configured" in result.output


def test_export_cmd_writes_configured_yaml_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    tool = List(
        id="L_1",
        name="Current: Tool",
        slug="current-tool",
        intent="Current",
        category="Tool",
        items=["pradyumnac/ghstars"],
    )
    star = make_star("pradyumnac/ghstars", description="a tool")
    store = StateStore(tmp_path / "state")
    store.save_stars([star])
    store.save_lists([tool])
    _use_store(monkeypatch, store)

    config_path = tmp_path / "export.toml"
    config_path.write_text(
        """
[[exports]]
name = "tools"
list_name = "Current: Tool"
output = "tools.yaml"
format = "yaml"
"""
    )
    _use_export_config(monkeypatch, config_path)

    output_dir = tmp_path / "cwd"
    output_dir.mkdir()
    monkeypatch.chdir(output_dir)

    result = runner.invoke(app, ["export"])

    assert result.exit_code == 0
    assert "Wrote 1 star(s) to" in result.output
    loaded = yaml.safe_load((output_dir / "tools.yaml").read_text())
    assert loaded == [
        {
            "full_name": "pradyumnac/ghstars",
            "html_url": star.html_url,
            "description": "a tool",
        }
    ]


def test_export_cmd_json_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    tool = List(
        id="L_1",
        name="Current: Tool",
        slug="current-tool",
        intent="Current",
        category="Tool",
        items=["pradyumnac/ghstars"],
    )
    star = make_star("pradyumnac/ghstars")
    store = StateStore(tmp_path / "state")
    store.save_stars([star])
    store.save_lists([tool])
    _use_store(monkeypatch, store)

    config_path = tmp_path / "export.toml"
    config_path.write_text(
        """
[[exports]]
name = "tools"
list_name = "Current: Tool"
output = "tools.json"
format = "json"
"""
    )
    _use_export_config(monkeypatch, config_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["export", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload == [
        {
            "name": "tools",
            "output": str(tmp_path / "tools.json"),
            "format": "json",
            "star_count": 1,
            "skipped_malformed_lists": [],
        }
    ]


def test_export_cmd_warns_about_skipped_malformed_lists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    malformed = List(
        id="L_1",
        name="explore- Tool",
        slug="explore-tool",
        malformed=True,
        items=["pradyumnac/ghstars"],
    )
    star = make_star("pradyumnac/ghstars")
    store = StateStore(tmp_path / "state")
    store.save_stars([star])
    store.save_lists([malformed])
    _use_store(monkeypatch, store)

    config_path = tmp_path / "export.toml"
    config_path.write_text(
        """
[[exports]]
name = "exploring"
category = "Tool"
intent = "Explore"
output = "exploring.yaml"
format = "yaml"
"""
    )
    _use_export_config(monkeypatch, config_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["export"])

    assert result.exit_code == 0
    assert "skipped malformed" in result.output
    assert "explore- Tool" in result.output


def test_export_cmd_fails_on_invalid_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path / "state")
    _use_store(monkeypatch, store)

    config_path = tmp_path / "export.toml"
    config_path.write_text("not valid [[ toml")
    _use_export_config(monkeypatch, config_path)

    result = runner.invoke(app, ["export"])

    assert result.exit_code == 1
    assert "error:" in result.output


def test_tui_cmd_is_registered_on_the_top_level_app() -> None:
    """`ghstars tui` (ticket 09) is wired in additively -- confirm it's
    listed without actually launching the Textual event loop, which
    needs a real terminal and would hang under `CliRunner`.
    """
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "tui" in result.output


def test_category_rename_cmd_renames_the_lifecycle_variants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    explore = List(id="L_explore", name="Explore: Old", slug="explore-old")
    current = List(id="L_current", name="Current: Old", slug="current-old")
    lists = [explore, current]
    store = StateStore(tmp_path)
    store.save_lists(lists)
    _use_store(monkeypatch, store)
    _use_client(monkeypatch, FakeGitHubClient(lists=lists))

    result = runner.invoke(app, ["category", "rename", "Old", "New"])

    assert result.exit_code == 0
    assert "Renamed 2 List(s) from 'Old' to 'New'." in result.output


def test_category_rename_cmd_reports_skipped_as_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stale_local = List(id="L_explore", name="Explore: Old", slug="explore-old")
    store = StateStore(tmp_path)
    store.save_lists([stale_local])
    _use_store(monkeypatch, store)
    live = List(id="L_explore", name="Explore: Elsewhere", slug="explore-elsewhere")
    _use_client(monkeypatch, FakeGitHubClient(lists=[live]))

    result = runner.invoke(app, ["category", "rename", "Old", "New", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload == {"renamed": [], "skipped": ["L_explore"]}


def test_category_rename_cmd_fails_when_category_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path)
    _use_store(monkeypatch, store)
    _use_client(monkeypatch, FakeGitHubClient())

    result = runner.invoke(app, ["category", "rename", "Nonexistent", "New"])

    assert result.exit_code == 1
    assert "no Explore/Current/Retired List found" in result.output


def test_category_drain_cmd_migrates_stars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    explore_old = List(
        id="L_1", name="Explore: Old", slug="explore-old", items=["pradyumnac/x"]
    )
    star = make_star("pradyumnac/x", list_ids=["L_1"])
    store = StateStore(tmp_path)
    store.save_lists([explore_old])
    store.save_stars([star])
    _use_store(monkeypatch, store)
    _use_client(monkeypatch, FakeGitHubClient(stars=[star], lists=[explore_old]))

    result = runner.invoke(app, ["category", "drain", "Old", "New"])

    assert result.exit_code == 0
    assert "Migrated 1 Star(s) from 'Old' to 'New'." in result.output


def test_category_drain_cmd_creates_a_private_destination_when_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    explore_old = List(
        id="L_1", name="Explore: Old", slug="explore-old", items=["pradyumnac/x"]
    )
    star = make_star("pradyumnac/x", list_ids=["L_1"])
    store = StateStore(tmp_path)
    store.save_lists([explore_old])
    store.save_stars([star])
    _use_store(monkeypatch, store)
    client = FakeGitHubClient(stars=[star], lists=[explore_old])
    _use_client(monkeypatch, client)

    result = runner.invoke(app, ["category", "drain", "Old", "New", "--private"])

    assert result.exit_code == 0
    created = next(lst for lst in client.fetch_lists() if lst.name == "Explore: New")
    assert created.is_private is True


def test_category_drain_cmd_reports_skipped_as_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    stale_local = List(
        id="L_1", name="Explore: Old", slug="explore-old", items=["pradyumnac/x"]
    )
    store = StateStore(tmp_path)
    store.save_lists([stale_local])
    star = make_star("pradyumnac/x", list_ids=[])
    store.save_stars([star])
    _use_store(monkeypatch, store)
    # Live: pradyumnac/x already left the source List since the snapshot.
    live = List(id="L_1", name="Explore: Old", slug="explore-old", items=[])
    _use_client(monkeypatch, FakeGitHubClient(stars=[star], lists=[live]))

    result = runner.invoke(app, ["category", "drain", "Old", "New", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload == {"migrated": [], "skipped": ["pradyumnac/x"]}


def test_category_drain_cmd_fails_when_category_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path)
    _use_store(monkeypatch, store)
    _use_client(monkeypatch, FakeGitHubClient())

    result = runner.invoke(app, ["category", "drain", "Nonexistent", "New"])

    assert result.exit_code == 1
    assert "no Explore/Current/Retired List found" in result.output
