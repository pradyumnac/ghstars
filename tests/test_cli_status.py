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
from ghstars.core.models import Intent, List, RetriageEntry, Star
from ghstars.core.state_store import StateStore
from ghstars.core.status import (
    build_status,
    stale_classification_warning,
    verify_state,
)

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
        "active_star_count": 0,
        "archived_star_count": 0,
        "list_count": 0,
        "unclassified_count": 0,
        "pending_edit_count": 0,
        "retriage_queue_count": 0,
        "verify_ok": True,
        "verify_problems": [],
        "warnings": [],
    }


def test_status_plain_text_reports_never_synced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path)
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "Last sync: never" in result.output
    assert "Active stars: 0" in result.output
    assert "Archived stars: 0" in result.output
    assert "Lists: 0" in result.output
    assert "Unclassified: 0" in result.output
    assert "Pending edits: 0" in result.output
    assert "Retriage Queue: 0" in result.output
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
    assert payload["active_star_count"] == 2
    assert payload["archived_star_count"] == 0
    assert payload["list_count"] == 1
    assert payload["retriage_queue_count"] == 1
    assert payload["unclassified_count"] == 1
    assert payload["pending_edit_count"] == 0
    assert payload["verify_ok"] is True
    assert payload["verify_problems"] == []


def test_status_json_counts_archived_stars_and_pending_edits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    active = make_star("example-owner/active")
    archived = make_star("example-owner/archived", archived=True)
    pending = make_star(
        "example-owner/pending", list_ids=["L_tool"], pending_list_ids=["L_other"]
    )
    store = StateStore(tmp_path)
    store.save_stars([active, archived, pending])
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["active_star_count"] == 2
    assert payload["archived_star_count"] == 1
    assert payload["pending_edit_count"] == 1


def test_status_never_creates_a_github_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path)
    _use_store(monkeypatch, store)

    def _boom() -> None:
        raise AssertionError("status must not create a GitHubClient")

    monkeypatch.setattr(cli_module, "get_client", _boom)

    result = runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 0


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


def _classified(list_id: str, name: str, intent: Intent, category: str) -> List:
    return List(
        id=list_id,
        name=name,
        slug=name.lower().replace(": ", "-").replace(" ", "-"),
        intent=intent,
        category=category,
    )


def test_status_warns_when_lists_predate_the_current_parser() -> None:
    """Since ADR 0005 a well-formed name always yields an Intent, so
    `intent=None, malformed=False` means an older parser wrote it -- and the
    Star-level checks cannot see such a List until the next sync.
    """
    stale = List(id="L_1", name="Vendored skills", slug="vendored-skills")

    warning = stale_classification_warning([stale])

    assert warning is not None
    assert "ghstars sync" in warning


def test_status_does_not_warn_on_freshly_classified_lists() -> None:
    fresh = _classified("L_1", "Explore: Tool", "Explore", "Tool")
    malformed = List(
        id="L_2", name="Exploring: Foo", slug="exploring-foo", malformed=True
    )

    assert stale_classification_warning([fresh, malformed]) is None


def test_verify_state_flags_an_unblessed_category() -> None:
    """Reported, never rejected -- different from `List.malformed` (ADR 0005)."""
    lst = _classified("L_1", "Explore: Tool - Dev", "Explore", "Tool - Dev")

    problems = verify_state([], [lst], categories=["Tool", "General"])

    assert any("unblessed Category 'Tool - Dev'" in p for p in problems)
    # The name shape is fine; only the value is unblessed.
    assert lst.malformed is False


def test_verify_state_accepts_a_blessed_category() -> None:
    lst = _classified("L_1", "Explore: Tool", "Explore", "Tool")

    assert verify_state([], [lst], categories=["Tool", "General"]) == []


def test_verify_state_skips_the_vocabulary_check_without_categories() -> None:
    """A caller with no config keeps the structural checks alone."""
    lst = _classified("L_1", "Explore: Wombat", "Explore", "Wombat")

    assert verify_state([], [lst]) == []


def test_verify_state_flags_a_star_in_the_triage_inbox_and_a_classified_list() -> None:
    inbox = _classified("L_1", "Explore: General", "Explore", "General")
    classified = _classified("L_2", "Explore: Tool", "Explore", "Tool")
    star = _star("example-owner/x", list_ids=["L_1", "L_2"])

    problems = verify_state([star], [inbox, classified])

    assert any("triage inbox" in p for p in problems)


def test_verify_state_allows_a_star_in_the_triage_inbox_alone() -> None:
    inbox = _classified("L_1", "Explore: General", "Explore", "General")
    star = _star("example-owner/x", list_ids=["L_1"])

    assert verify_state([star], [inbox]) == []


def test_verify_state_flags_two_lifecycle_intents_on_one_star() -> None:
    """At most one of Explore/Current/Retired applies per Star (ADR 0005)."""
    current = _classified("L_1", "Current: Tool", "Current", "Tool")
    explore = _classified("L_2", "Explore: AI Agents", "Explore", "AI Agents")
    star = _star("example-owner/x", list_ids=["L_1", "L_2"])

    problems = verify_state([star], [current, explore])

    assert any("two lifecycle Intents" in p for p in problems)


def test_verify_state_allows_a_lifecycle_intent_beside_reference_and_learn() -> None:
    current = _classified("L_1", "Current: Tool", "Current", "Tool")
    reference = _classified("L_2", "Reference: AI Agents", "Reference", "AI Agents")
    learn = _classified("L_3", "Learn: Example", "Learn", "Example")
    star = _star("example-owner/x", list_ids=["L_1", "L_2", "L_3"])

    assert verify_state([star], [current, reference, learn]) == []


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
