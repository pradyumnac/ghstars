"""Tests for `ghstars status` (ticket 08).

Offline: builds the report from `StateStore.load_*()` only, no
`GitHubClient` involved -- so every test here only ever needs `_use_store`.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest import NOW, StarFactory
from typer.testing import CliRunner

import ghstars.cli as cli_module
from ghstars.cli import app
from ghstars.core.models import List, RetriageEntry, Star
from ghstars.core.state_store import StateStore
from ghstars.core.status import build_status, verify_state

runner = CliRunner()


def _use_store(monkeypatch: pytest.MonkeyPatch, store: StateStore) -> None:
    monkeypatch.setattr(cli_module, "get_store", lambda: store)
    monkeypatch.setattr(cli_module, "ensure_config_dir", lambda: store.base_dir)


def test_status_json_reports_empty_state_before_any_sync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path)
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "last_sync_at": None,
        "retriage_queue_count": 0,
        "unclassified_count": 0,
        "verify_ok": True,
        "verify_problems": [],
    }


def test_status_plain_text_reports_never_synced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path)
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "Last sync: never" in result.output
    assert "Retriage Queue: 0" in result.output
    assert "Unclassified: 0" in result.output
    assert "Verify: ok" in result.output


def test_status_json_counts_mixed_classified_unclassified_and_retriage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    current_tool = List(id="L_tool", name="Current: Tool", slug="current-tool")
    later = datetime(2026, 8, 20, tzinfo=UTC)
    classified = make_star(
        "example-owner/classified", list_ids=["L_tool"], last_checked=NOW
    )
    unclassified = make_star(
        "example-owner/unclassified", list_ids=[], last_checked=later
    )
    store = StateStore(tmp_path)
    store.save_lists([current_tool])
    store.save_stars([classified, unclassified])
    store.save_retriage(
        [
            RetriageEntry(
                star_full_name="example-owner/classified",
                attempted_list_ids=["L_tool"],
                conflict_detected_at=NOW,
                resolved=False,
            ),
            RetriageEntry(
                star_full_name="example-owner/resolved",
                attempted_list_ids=["L_tool"],
                conflict_detected_at=NOW,
                resolved=True,
            ),
        ]
    )
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["last_sync_at"] == later.isoformat().replace("+00:00", "Z")
    assert payload["retriage_queue_count"] == 1
    assert payload["unclassified_count"] == 1
    assert payload["verify_ok"] is True
    assert payload["verify_problems"] == []


def test_status_verify_fails_on_dangling_list_id_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    star = make_star("example-owner/x", list_ids=["L_missing"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["verify_ok"] is False
    assert len(payload["verify_problems"]) == 1
    assert "L_missing" in payload["verify_problems"][0]


def test_status_plain_text_reports_verify_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    star = make_star("example-owner/x", list_ids=["L_missing"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "Verify: FAILED (1 problem(s))" in result.output
    assert "L_missing" in result.output


def test_verify_state_flags_duplicate_full_names() -> None:
    star = _star("example-owner/x")
    problems = verify_state([star, star], [])

    assert any("duplicate Star.full_name" in p for p in problems)


def test_verify_state_flags_duplicate_list_ids() -> None:
    lst = List(id="L_1", name="Explore: Tool", slug="explore-tool")
    problems = verify_state([], [lst, lst])

    assert any("duplicate List.id" in p for p in problems)


def test_verify_state_passes_on_clean_state() -> None:
    lst = List(id="L_1", name="Explore: Tool", slug="explore-tool")
    star = _star("example-owner/x", list_ids=["L_1"])

    assert verify_state([star], [lst]) == []


def test_build_status_handles_a_completely_empty_store(
    tmp_path: Path,
) -> None:
    store = StateStore(tmp_path)
    report = build_status(store)

    assert report.last_sync_at is None
    assert report.verify_ok is True


def _star(full_name: str, **overrides: object) -> Star:
    defaults = {
        "full_name": full_name,
        "html_url": f"https://github.com/{full_name}",
        "starred_at": NOW,
        "first_seen": NOW,
        "last_checked": NOW,
    }
    return Star.model_validate(defaults | overrides)
