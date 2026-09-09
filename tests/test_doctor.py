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
    """A blessed Category with no List is an opportunity, not a defect, so
    it is reported without making the account not-ok. Otherwise `ok` would
    be false forever -- the default vocabulary ships 12 Categories.
    """
    report = diagnose([_list("L1", "Explore: Tool")], categories=VOCAB)

    assert report.missing_categories == ["General", "Library"]
    assert report.ok is True


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


def test_diagnose_flags_a_star_in_the_inbox_and_a_classified_list() -> None:
    inbox = List(
        id="L1", name="Explore: General", slug="explore-general", items=["owner/x"]
    )
    tool = List(id="L2", name="Explore: Tool", slug="explore-tool", items=["owner/x"])

    report = diagnose([inbox, tool], categories=VOCAB)

    assert report.ok is False
    problem = report.star_problems[0]
    assert problem.full_name == "owner/x"
    assert problem.in_triage_inbox == ["Explore: General"]
    assert problem.classified == ["Explore: Tool"]
    assert problem.repairs == ["ghstars untag owner/x 'Explore: General'"]


def test_diagnose_flags_two_lifecycle_intents_on_one_star() -> None:
    """`tag`'s strip is per-Category by design, so it creates this state
    freely -- the live reporter must not be blind to it (ADR 0005).
    """
    explore = List(
        id="L1", name="Explore: Tool", slug="explore-tool", items=["owner/x"]
    )
    current = List(
        id="L2", name="Current: Library", slug="current-library", items=["owner/x"]
    )

    report = diagnose([explore, current], categories=VOCAB)

    assert report.ok is False
    problem = next(
        p for p in report.star_problems if p.problem == "two_lifecycle_intents"
    )
    assert problem.lifecycle_intents == ["Current", "Explore"]


def test_diagnose_and_verify_state_agree_on_star_rules() -> None:
    """Both call `taxonomy.star_conflicts`, so they cannot diverge."""
    from conftest import NOW

    from ghstars.core.models import Star
    from ghstars.core.status import verify_state
    from ghstars.core.taxonomy import classify_list

    explore = List(
        id="L1", name="Explore: Tool", slug="explore-tool", items=["owner/x"]
    )
    current = List(
        id="L2", name="Current: Library", slug="current-library", items=["owner/x"]
    )
    star = Star(
        full_name="owner/x",
        html_url="https://github.com/owner/x",
        starred_at=NOW,
        first_seen=NOW,
        last_checked=NOW,
        list_ids=["L1", "L2"],
    )

    live = diagnose([explore, current], categories=VOCAB)
    # `verify_state` reads the classification `sync` stored; `diagnose`
    # derives it live. Same rules underneath either way.
    local = verify_state(
        [star], [classify_list(explore), classify_list(current)], categories=VOCAB
    )

    assert any(p.problem == "two_lifecycle_intents" for p in live.star_problems)
    assert any("two lifecycle Intents" in problem for problem in local)


def test_repair_commands_are_shell_quoted() -> None:
    """`repr` emits double quotes for a name holding an apostrophe, and a
    shell expands `$(...)` inside those. `shlex.quote` does not.
    """
    import shlex

    name = "Exploring: it's $(whoami)"
    hostile = List(id="L1", name=name, slug="x", items=["owner/x"])

    report = diagnose([hostile], categories=VOCAB)

    # A shell parsing the suggestion recovers the name verbatim, with no
    # substitution performed on it.
    argv = shlex.split(report.problems[0].repairs[0])
    assert name in argv


def test_malformed_repair_command_includes_yes() -> None:
    """The suggested command must work verbatim; rename-list requires --yes."""
    report = diagnose([_list("L1", "Exploring: Foo")], categories=VOCAB)

    assert report.problems[0].repairs[0].endswith("--yes")


def test_inbox_repair_declares_that_it_needs_a_sync() -> None:
    """`untag` reads local state, so a JSON caller needs the prerequisite."""
    inbox = _list("L1", "Explore: General")
    tool = _list("L2", "Explore: Tool")
    inbox.items.append("owner/x")
    tool.items.append("owner/x")

    report = diagnose([inbox, tool], categories=VOCAB)

    assert report.star_problems[0].requires_sync is True


def test_diagnose_allows_a_star_in_the_inbox_alone() -> None:
    inbox = List(
        id="L1", name="Explore: General", slug="explore-general", items=["owner/x"]
    )

    report = diagnose([inbox], categories=VOCAB)

    assert report.star_problems == []


def test_doctor_cli_suggests_the_untag_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inbox = _list("L1", "Explore: General")
    tool = _list("L2", "Explore: Tool")
    client = FakeGitHubClient(
        lists=[
            inbox.model_copy(update={"items": ["owner/x"]}),
            tool.model_copy(update={"items": ["owner/x"]}),
        ]
    )
    _use(monkeypatch, StateStore(tmp_path), client)

    result = runner.invoke(app, ["doctor"])

    assert "ghstars untag owner/x 'Explore: General'" in result.output


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
