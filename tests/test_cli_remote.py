"""Tests for `ghstars remote` (ADR 0005): the write side of `doctor`.

`doctor` reports; each kind of repair is its own verb here.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import ghstars.cli as cli_module
from ghstars.cli import app
from ghstars.core.doctor import ListNameTakenError, ListNotFoundError, rename_list
from ghstars.core.fake_client import FakeGitHubClient
from ghstars.core.models import List
from ghstars.core.state_store import StateStore
from ghstars.core.taxonomy import UnwritableListNameError

runner = CliRunner()

VOCAB = ["Tool", "Library", "General"]


def _use(
    monkeypatch: pytest.MonkeyPatch, store: StateStore, client: FakeGitHubClient
) -> None:
    store.base_dir.mkdir(parents=True, exist_ok=True)
    config_path = store.base_dir / "ghstars.toml"
    config_path.write_text(f"[taxonomy]\ncategories = {json.dumps(VOCAB)}\n")

    monkeypatch.setattr(cli_module, "get_store", lambda: store)
    monkeypatch.setattr(cli_module, "get_client", lambda: client)
    monkeypatch.setattr(cli_module, "ensure_config_dir", lambda: store.base_dir)
    monkeypatch.setattr(cli_module, "get_core_config_path", lambda: config_path)


def _list(list_id: str, name: str) -> List:
    return List(id=list_id, name=name, slug=name.lower().replace(" ", "-"))


# -- bootstrap ----------------------------------------------------------------


def test_bootstrap_requires_yes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = FakeGitHubClient(lists=[_list("L1", "Explore: Tool")])
    _use(monkeypatch, StateStore(tmp_path), client)

    result = runner.invoke(app, ["remote", "bootstrap", "--intent", "Explore"])

    assert result.exit_code != 0
    assert len(client.fetch_lists()) == 1


def test_bootstrap_requires_an_explicit_intent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ghstars never guesses an Intent (ticket 03)."""
    client = FakeGitHubClient(lists=[_list("L1", "Explore: Tool")])
    _use(monkeypatch, StateStore(tmp_path), client)

    result = runner.invoke(app, ["remote", "bootstrap", "--yes"])

    assert result.exit_code != 0
    assert len(client.fetch_lists()) == 1


def test_bootstrap_is_blocked_by_a_name_needing_attention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rename can turn an unblessed Category blessed, so names come first."""
    client = FakeGitHubClient(lists=[_list("L1", "Explore: Wombat")])
    _use(monkeypatch, StateStore(tmp_path), client)

    result = runner.invoke(app, ["remote", "bootstrap", "--yes", "--intent", "Explore"])

    assert result.exit_code != 0
    assert len(client.fetch_lists()) == 1


def test_bootstrap_force_overrides_the_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = FakeGitHubClient(lists=[_list("L1", "Explore: Wombat")])
    _use(monkeypatch, StateStore(tmp_path), client)

    runner.invoke(
        app, ["remote", "bootstrap", "--yes", "--intent", "Explore", "--force"]
    )

    names = sorted(lst.name for lst in client.fetch_lists())
    assert names == [
        "Explore: General",
        "Explore: Library",
        "Explore: Tool",
        "Explore: Wombat",
    ]


def test_bootstrap_creates_the_whole_missing_set_for_one_intent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Named for seeding a taxonomy, not for creating one List."""
    client = FakeGitHubClient(lists=[_list("L1", "Learn: Tool")])
    _use(monkeypatch, StateStore(tmp_path), client)

    result = runner.invoke(
        app, ["remote", "bootstrap", "--yes", "--intent", "Learn", "--json"]
    )

    assert json.loads(result.output)["created"] == [
        "Learn: General",
        "Learn: Library",
    ]


# -- rename-list --------------------------------------------------------------


def test_bootstrap_limits_to_the_named_categories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing Categories can need different Intents, so a run must be able
    to take a subset -- otherwise the first run claims all of them.
    """
    client = FakeGitHubClient(lists=[_list("L1", "Explore: Tool")])
    _use(monkeypatch, StateStore(tmp_path), client)

    result = runner.invoke(
        app,
        [
            "remote", "bootstrap", "--yes", "--intent", "Reference",
            "--category", "Library", "--json",
        ],
    )

    assert json.loads(result.output)["created"] == ["Reference: Library"]


def test_bootstrap_writes_the_explicit_reference_form(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bare name would parse to Reference too, but ghstars writes the
    Intent it means rather than leaning on the default (ADR 0005).
    """
    client = FakeGitHubClient(lists=[_list("L1", "Explore: Tool")])
    _use(monkeypatch, StateStore(tmp_path), client)

    runner.invoke(
        app,
        ["remote", "bootstrap", "--yes", "--intent", "Reference", "--category", "General"],
    )

    assert "Reference: General" in [lst.name for lst in client.fetch_lists()]


def test_rename_list_changes_one_lists_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = FakeGitHubClient(lists=[_list("L1", "Explore: Tool")])
    _use(monkeypatch, StateStore(tmp_path), client)

    result = runner.invoke(
        app, ["remote", "rename-list", "Explore: Tool", "Explore: Library", "--yes"]
    )

    assert result.exit_code == 0
    assert [lst.name for lst in client.fetch_lists()] == ["Explore: Library"]


def test_rename_list_can_change_the_intent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gap `category rename` cannot close -- it keeps each List's Intent."""
    client = FakeGitHubClient(lists=[_list("L1", "Learning")])
    _use(monkeypatch, StateStore(tmp_path), client)

    result = runner.invoke(
        app, ["remote", "rename-list", "Learning", "Learn: General", "--yes", "--json"]
    )

    payload = json.loads(result.output)
    assert payload["name"] == "Learn: General"
    assert payload["intent"] == "Learn"
    assert payload["category"] == "General"


def test_rename_list_requires_yes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = FakeGitHubClient(lists=[_list("L1", "Explore: Tool")])
    _use(monkeypatch, StateStore(tmp_path), client)

    result = runner.invoke(
        app, ["remote", "rename-list", "Explore: Tool", "Explore: Library"]
    )

    assert result.exit_code != 0
    assert [lst.name for lst in client.fetch_lists()] == ["Explore: Tool"]


def test_rename_list_refuses_an_unblessed_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It exists to move a List out of a bad name, never into one."""
    client = FakeGitHubClient(lists=[_list("L1", "Explore: Tool")])
    _use(monkeypatch, StateStore(tmp_path), client)

    result = runner.invoke(
        app, ["remote", "rename-list", "Explore: Tool", "Explore: Wombat", "--yes"]
    )

    assert result.exit_code != 0
    assert [lst.name for lst in client.fetch_lists()] == ["Explore: Tool"]


def test_rename_list_refuses_a_malformed_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = FakeGitHubClient(lists=[_list("L1", "Explore: Tool")])
    _use(monkeypatch, StateStore(tmp_path), client)

    result = runner.invoke(
        app, ["remote", "rename-list", "Explore: Tool", "Exploring: Tool", "--yes"]
    )

    assert result.exit_code != 0


# -- core ---------------------------------------------------------------------


def test_rename_list_raises_when_the_list_is_missing() -> None:
    client = FakeGitHubClient()

    with pytest.raises(ListNotFoundError):
        rename_list(client, "Explore: Ghost", "Explore: Tool", categories=VOCAB)


def test_rename_list_raises_when_the_target_name_is_taken() -> None:
    client = FakeGitHubClient(
        lists=[_list("L1", "Explore: Tool"), _list("L2", "Explore: Library")]
    )

    with pytest.raises(ListNameTakenError):
        rename_list(client, "Explore: Tool", "Explore: Library", categories=VOCAB)


def test_rename_list_refuses_to_write_a_bad_name() -> None:
    client = FakeGitHubClient(lists=[_list("L1", "Explore: Tool")])

    with pytest.raises(UnwritableListNameError):
        rename_list(client, "Explore: Tool", "Exploring: Tool", categories=VOCAB)


def test_rename_list_is_a_no_op_when_the_name_is_unchanged() -> None:
    client = FakeGitHubClient(lists=[_list("L1", "Explore: Tool")])

    result = rename_list(client, "Explore: Tool", "Explore: Tool", categories=VOCAB)

    assert result.name == "Explore: Tool"


def test_rename_list_rejects_a_same_name_no_op_on_a_bad_name() -> None:
    """Pasting the old string back must not report a repair that never
    happened -- validation runs before the no-op check.
    """
    client = FakeGitHubClient(lists=[_list("L1", "Exploring: Foo")])

    with pytest.raises(UnwritableListNameError):
        rename_list(client, "Exploring: Foo", "Exploring: Foo", categories=VOCAB)


def test_rename_list_rejects_a_target_matching_another_lists_identity() -> None:
    """`Explore: AI_Agents` and `Explore: AI Agents` are one Category, and a
    duplicate of that shape is one nothing downstream can flag.
    """
    client = FakeGitHubClient(
        lists=[_list("L1", "Widgets"), _list("L2", "Explore: AI Agents")]
    )

    with pytest.raises(ListNameTakenError):
        rename_list(
            client,
            "Widgets",
            "Explore: AI_Agents",
            categories=[*VOCAB, "AI Agents", "Widgets"],
        )
