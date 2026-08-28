"""Tests for the `ghstars` CLI's `retriage` command (ticket 05).

Uses typer's own `CliRunner` -- no network, no real GitHub client. `main()`'s
`@app.callback()` calls `ensure_config_dir()`, which touches the real
`~/.ghstars/config` directory by default; every test here monkeypatches it
to a no-op alongside `get_store`, so nothing outside `tmp_path` is touched.
"""

import contextlib
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from types import TracebackType

import pytest
import yaml
from conftest import NOW, StarFactory
from filelock import Timeout
from typer.testing import CliRunner

import ghstars.cli as cli_module
from ghstars.cli import app
from ghstars.core.fake_client import FakeGitHubClient
from ghstars.core.github_client import GitHubClient
from ghstars.core.models import List, RateLimitStatus, RetriageEntry
from ghstars.core.state_store import StateStore
from ghstars.github import GitHubApiError

runner = CliRunner()


def _use_store(monkeypatch: pytest.MonkeyPatch, store: StateStore) -> None:
    monkeypatch.setattr(cli_module, "get_store", lambda: store)
    monkeypatch.setattr(cli_module, "ensure_config_dir", lambda: store.base_dir)


def _use_client(monkeypatch: pytest.MonkeyPatch, client: GitHubClient) -> None:
    monkeypatch.setattr(cli_module, "get_client", lambda: client)


def _use_core_config(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    monkeypatch.setattr(cli_module, "get_core_config_path", lambda: path)


class _TimeoutOnEnter:
    """A context manager that raises `Timeout` on entry, never on exit."""

    def __init__(self, lock_path: str) -> None:
        self._lock_path = lock_path

    def __enter__(self) -> None:
        raise Timeout(self._lock_path)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


def _make_lock_time_out(store: StateStore) -> None:
    """Simulate a concurrent `ghstars` command already holding the lock."""
    lock_path = str(store.base_dir / "state" / ".lock")
    store.lock = lambda timeout=None: _TimeoutOnEnter(lock_path)  # type: ignore[assignment,method-assign,return-value]


def test_retriage_json_lists_queue_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path)
    entry = RetriageEntry(
        star_full_name="example-owner/x",
        attempted_list_ids=["L_1"],
        conflict_detected_at=NOW,
    )
    store.save_retriage([entry])
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["retriage", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "total": 1,
        "offset": 0,
        "limit": None,
        "rows": [
            {
                "star_full_name": "example-owner/x",
                "attempted_list_ids": ["L_1"],
                "conflict_detected_at": "2026-08-16T00:00:00Z",
                "resolved": False,
            }
        ],
    }


def test_retriage_json_is_an_empty_list_when_the_queue_is_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path)
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["retriage", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "total": 0,
        "offset": 0,
        "limit": None,
        "rows": [],
    }


def test_retriage_json_empty_fields_string_means_no_restriction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--fields ""` strips to no field names; must fall back to every
    field, matching `--fields` being omitted entirely -- not to an empty
    record. Regression test for ticket 31 Scope D's `select_fields`
    call site, which took an unfiltered empty list literally.
    """
    store = StateStore(tmp_path)
    entry = RetriageEntry(
        star_full_name="example-owner/x",
        attempted_list_ids=["L_1"],
        conflict_detected_at=NOW,
    )
    store.save_retriage([entry])
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["retriage", "--json", "--fields", ""])

    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "total": 1,
        "offset": 0,
        "limit": None,
        "rows": [
            {
                "star_full_name": "example-owner/x",
                "attempted_list_ids": ["L_1"],
                "conflict_detected_at": "2026-08-16T00:00:00Z",
                "resolved": False,
            }
        ],
    }


def test_retriage_details_flag_selects_the_detailed_field_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path)
    entry = RetriageEntry(
        star_full_name="example-owner/x",
        attempted_list_ids=["L_1"],
        conflict_detected_at=NOW,
    )
    store.save_retriage([entry])
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["retriage", "--json", "--details"])

    [row] = json.loads(result.output)["rows"]
    assert set(row) == set(RetriageEntry.model_fields)


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
    current = List(
        id="L_current",
        name="Current: Tool",
        slug="current-tool",
        items=["example-owner/ghstars"],
    )
    retired = List(id="L_retired", name="Retired: Tool", slug="retired-tool")
    star = make_star("example-owner/ghstars", list_ids=["L_current"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([current, retired])
    _use_store(monkeypatch, store)
    _use_client(monkeypatch, FakeGitHubClient(stars=[star], lists=[current, retired]))

    result = runner.invoke(app, ["tag", "example-owner/ghstars", "Retired: Tool"])

    assert result.exit_code == 0
    assert "removed from 1 other List(s)" in result.output


def test_tag_cmd_reports_removed_list_ids_as_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    current = List(
        id="L_current",
        name="Current: Tool",
        slug="current-tool",
        items=["example-owner/ghstars"],
    )
    retired = List(id="L_retired", name="Retired: Tool", slug="retired-tool")
    star = make_star("example-owner/ghstars", list_ids=["L_current"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([current, retired])
    _use_store(monkeypatch, store)
    _use_client(monkeypatch, FakeGitHubClient(stars=[star], lists=[current, retired]))

    result = runner.invoke(
        app, ["tag", "example-owner/ghstars", "Retired: Tool", "--json"]
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["removed_list_ids"] == ["L_current"]
    assert payload["list_ids"] == ["L_retired"]


def test_tag_cmd_reports_no_removed_list_ids_when_nothing_stripped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    tool = List(id="L_tool", name="Explore: Tool", slug="explore-tool")
    star = make_star("example-owner/ghstars")
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([tool])
    _use_store(monkeypatch, store)
    _use_client(monkeypatch, FakeGitHubClient(stars=[star], lists=[tool]))

    result = runner.invoke(app, ["tag", "example-owner/ghstars", "Explore: Tool"])

    assert result.exit_code == 0
    assert "removed from" not in result.output


def test_export_cmd_reports_no_exports_configured_when_no_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path / "state")
    _use_store(monkeypatch, store)
    _use_core_config(monkeypatch, tmp_path / "ghstars.toml")

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
        items=["example-owner/ghstars"],
    )
    # `list_ids` is the membership source `select_stars` resolves through
    # (see `core/export.py`); `items` above is set too since `sync()`
    # keeps both reconciled in practice.
    star = make_star("example-owner/ghstars", description="a tool", list_ids=["L_1"])
    store = StateStore(tmp_path / "state")
    store.save_stars([star])
    store.save_lists([tool])
    _use_store(monkeypatch, store)

    config_path = tmp_path / "ghstars.toml"
    config_path.write_text(
        """
[[export.exports]]
name = "tools"
list_name = "Current: Tool"
output = "tools.yaml"
format = "yaml"
"""
    )
    _use_core_config(monkeypatch, config_path)

    output_dir = tmp_path / "cwd"
    output_dir.mkdir()
    monkeypatch.chdir(output_dir)

    result = runner.invoke(app, ["export"])

    assert result.exit_code == 0
    assert "Wrote 1 star(s) to" in result.output
    loaded = yaml.safe_load((output_dir / "tools.yaml").read_text())
    assert loaded == [
        {
            "full_name": "example-owner/ghstars",
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
        items=["example-owner/ghstars"],
    )
    star = make_star("example-owner/ghstars", list_ids=["L_1"])
    store = StateStore(tmp_path / "state")
    store.save_stars([star])
    store.save_lists([tool])
    _use_store(monkeypatch, store)

    config_path = tmp_path / "ghstars.toml"
    config_path.write_text(
        """
[[export.exports]]
name = "tools"
list_name = "Current: Tool"
output = "tools.json"
format = "json"
"""
    )
    _use_core_config(monkeypatch, config_path)
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
        items=["example-owner/ghstars"],
    )
    star = make_star("example-owner/ghstars")
    store = StateStore(tmp_path / "state")
    store.save_stars([star])
    store.save_lists([malformed])
    _use_store(monkeypatch, store)

    config_path = tmp_path / "ghstars.toml"
    config_path.write_text(
        """
[[export.exports]]
name = "exploring"
category = "Tool"
intent = "Explore"
output = "exploring.yaml"
format = "yaml"
"""
    )
    _use_core_config(monkeypatch, config_path)
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

    config_path = tmp_path / "ghstars.toml"
    config_path.write_text("not valid [[ toml")
    _use_core_config(monkeypatch, config_path)

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
    assert "stars" in result.output
    assert "github-lists" in result.output
    assert "facets" in result.output
    assert "ratelimit" in result.output


def test_help_shows_current_export_config_path() -> None:
    result = runner.invoke(app, ["export", "--help"])

    assert result.exit_code == 0
    assert "[export]" in result.output
    assert "ghstars.toml" in result.output


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
        id="L_1", name="Explore: Old", slug="explore-old", items=["example-owner/x"]
    )
    star = make_star("example-owner/x", list_ids=["L_1"])
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
        id="L_1", name="Explore: Old", slug="explore-old", items=["example-owner/x"]
    )
    star = make_star("example-owner/x", list_ids=["L_1"])
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
        id="L_1", name="Explore: Old", slug="explore-old", items=["example-owner/x"]
    )
    store = StateStore(tmp_path)
    store.save_lists([stale_local])
    star = make_star("example-owner/x", list_ids=[])
    store.save_stars([star])
    _use_store(monkeypatch, store)
    # Live: example-owner/x already left the source List since the snapshot.
    live = List(id="L_1", name="Explore: Old", slug="explore-old", items=[])
    _use_client(monkeypatch, FakeGitHubClient(stars=[star], lists=[live]))

    result = runner.invoke(app, ["category", "drain", "Old", "New", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload == {"migrated": [], "skipped": ["example-owner/x"]}


def test_category_drain_cmd_fails_when_category_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path)
    _use_store(monkeypatch, store)
    _use_client(monkeypatch, FakeGitHubClient())

    result = runner.invoke(app, ["category", "drain", "Nonexistent", "New"])

    assert result.exit_code == 1
    assert "no Explore/Current/Retired List found" in result.output


@contextlib.contextmanager
def _reset_fetcher_logger() -> Iterator[logging.Logger]:
    fetcher_logger = logging.getLogger("ghstars.github")
    prev_level = fetcher_logger.level
    prev_handlers = list(fetcher_logger.handlers)
    prev_propagate = fetcher_logger.propagate
    try:
        yield fetcher_logger
    finally:
        fetcher_logger.setLevel(prev_level)
        fetcher_logger.propagate = prev_propagate
        for handler in list(fetcher_logger.handlers):
            if handler not in prev_handlers:
                fetcher_logger.removeHandler(handler)


def test_sync_cmd_debug_flag_prints_plain_stage_lines_and_raises_logger_level(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    store = StateStore(tmp_path)
    _use_store(monkeypatch, store)
    _use_client(monkeypatch, FakeGitHubClient())

    with _reset_fetcher_logger() as fetcher_logger, caplog.at_level(logging.WARNING):
        fetcher_logger.setLevel(logging.WARNING)

        result = runner.invoke(app, ["sync", "--debug"])

        assert result.exit_code == 0
        # Plain stage lines keep debug output readable.
        assert "Fetching starred repos..." in result.output
        assert fetcher_logger.level == logging.DEBUG


def test_sync_cmd_debug_env_var_also_enables_debug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    store = StateStore(tmp_path)
    _use_store(monkeypatch, store)
    _use_client(monkeypatch, FakeGitHubClient())
    monkeypatch.setenv("GHSTARS_DEBUG", "1")

    with _reset_fetcher_logger() as fetcher_logger, caplog.at_level(logging.WARNING):
        fetcher_logger.setLevel(logging.WARNING)

        result = runner.invoke(app, ["sync"])

        assert result.exit_code == 0
        assert "Fetching starred repos..." in result.output
        assert fetcher_logger.level == logging.DEBUG


def test_sync_cmd_debug_env_var_non_boolean_value_still_enables_debug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    store = StateStore(tmp_path)
    _use_store(monkeypatch, store)
    _use_client(monkeypatch, FakeGitHubClient())
    monkeypatch.setenv("GHSTARS_DEBUG", "verbose")

    with _reset_fetcher_logger() as fetcher_logger, caplog.at_level(logging.WARNING):
        fetcher_logger.setLevel(logging.WARNING)

        result = runner.invoke(app, ["sync"])

        assert result.exit_code == 0
        assert fetcher_logger.level == logging.DEBUG


def test_sync_cmd_json_reports_ordered_stages_and_final_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    _use_store(monkeypatch, store)
    _use_client(monkeypatch, FakeGitHubClient(stars=[make_star()]))

    result = runner.invoke(app, ["sync", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["stages"] == [
        "Checking rate limit",
        "Fetching starred repos",
        "Fetching Lists",
        "Pushing pending tag changes",
        "Saving local state",
    ]
    assert payload["star_count"] == 1
    assert payload["list_count"] == 0
    assert payload["failed_tag_pushes"] == []


def test_ratelimit_cmd_json_reports_the_live_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path)
    _use_store(monkeypatch, store)
    _use_client(
        monkeypatch,
        FakeGitHubClient(
            rate_limit=RateLimitStatus(remaining=4999, limit=5000, ok=True)
        ),
    )

    result = runner.invoke(app, ["ratelimit", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "remaining": 4999,
        "limit": 5000,
        "ok": True,
    }


def test_ratelimit_cmd_reports_network_failure_as_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path)
    _use_store(monkeypatch, store)

    class _BrokenClient(FakeGitHubClient):
        def check_rate_limit(self) -> RateLimitStatus:
            raise GitHubApiError("network down")

    _use_client(monkeypatch, _BrokenClient())
    result = runner.invoke(app, ["ratelimit", "--json"])

    assert result.exit_code == 3
    assert result.stdout == ""
    assert json.loads(result.stderr)["error"]["code"] == "network_failure"


def test_ratelimit_cmd_never_runs_a_full_sync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path)
    _use_store(monkeypatch, store)
    _use_client(
        monkeypatch,
        FakeGitHubClient(rate_limit=RateLimitStatus(remaining=1, limit=5000, ok=True)),
    )

    result = runner.invoke(app, ["ratelimit", "--json"])

    assert result.exit_code == 0
    # `fetch_stars`/`fetch_lists` were never called; state stays empty.
    assert store.load_stars() == []
    assert store.load_lists() == []


def test_sync_cmd_fails_gracefully_when_lock_is_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path)
    _make_lock_time_out(store)
    _use_store(monkeypatch, store)
    _use_client(monkeypatch, FakeGitHubClient())

    result = runner.invoke(app, ["sync"])

    assert result.exit_code == 3
    assert "could not acquire the local state lock" in result.output


def test_unstar_cmd_fails_gracefully_when_lock_is_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    star = make_star("example-owner/x", list_ids=[])
    store = StateStore(tmp_path)
    store.save_stars([star])
    _make_lock_time_out(store)
    _use_store(monkeypatch, store)
    _use_client(monkeypatch, FakeGitHubClient(stars=[star]))

    result = runner.invoke(app, ["unstar", "example-owner/x", "--yes"])

    assert result.exit_code == 3
    assert "unstarred example-owner/x on GitHub" in result.output
    assert "could not acquire the local state lock" in result.output


def test_category_rename_cmd_fails_gracefully_when_lock_is_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old_list = List(id="L_1", name="Explore: Old", slug="explore-old")
    store = StateStore(tmp_path)
    store.save_lists([old_list])
    _make_lock_time_out(store)
    _use_store(monkeypatch, store)
    _use_client(monkeypatch, FakeGitHubClient(lists=[old_list]))

    result = runner.invoke(app, ["category", "rename", "Old", "New"])

    assert result.exit_code == 3
    assert "could not acquire the local state lock" in result.output
