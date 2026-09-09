"""Tests for `ghstars taxonomy bless` (ADR 0002 as amended by ADR 0005)."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

import ghstars.cli as cli_module
from ghstars.cli import app
from ghstars.core.taxonomy import DEFAULT_CATEGORIES
from ghstars.core.vocabulary import BlessError, bless_category

runner = CliRunner()


def test_bless_preserves_comments_and_formatting(tmp_path: Path) -> None:
    """ADR 0002 protects `config/` being hand-editable and git-diffable, so
    a write must round-trip rather than regenerate the file.
    """
    path = tmp_path / "ghstars.toml"
    path.write_text(
        "# my own note\n[taxonomy]\n# kinds\ncategories = [\n  'Tool',\n]\n"
    )

    bless_category(path, "Wombat")

    text = path.read_text()
    assert "# my own note" in text
    assert "# kinds" in text
    assert "Wombat" in text


def test_bless_seeds_from_defaults_when_no_table_exists(tmp_path: Path) -> None:
    """Blessing one word must not silently drop the other eleven defaults."""
    path = tmp_path / "ghstars.toml"

    bless_category(path, "Wombat")

    text = path.read_text()
    for default in DEFAULT_CATEGORIES:
        assert default in text


def test_bless_normalizes(tmp_path: Path) -> None:
    path = tmp_path / "ghstars.toml"

    assert bless_category(path, "AI_Agents") == "AI Agents"


def test_bless_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "ghstars.toml"
    bless_category(path, "Wombat")
    first = path.read_text()

    bless_category(path, "Wombat")

    assert path.read_text() == first


def test_bless_rejects_a_category_that_normalizes_to_nothing(tmp_path: Path) -> None:
    """The same rule config load enforces: it would let bootstrap write
    `Explore: `, a malformed name.
    """
    with pytest.raises(BlessError):
        bless_category(tmp_path / "ghstars.toml", "___")


def test_bless_rejects_invalid_toml(tmp_path: Path) -> None:
    path = tmp_path / "ghstars.toml"
    path.write_text("[taxonomy\nbroken")

    with pytest.raises(BlessError):
        bless_category(path, "Wombat")


def test_bless_cli_writes_the_configured_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "ghstars.toml"
    monkeypatch.setattr(cli_module, "get_core_config_path", lambda: path)
    monkeypatch.setattr(cli_module, "ensure_config_dir", lambda: tmp_path)

    result = runner.invoke(app, ["taxonomy", "bless", "Wombat"])

    assert result.exit_code == 0
    assert "Wombat" in path.read_text()


def test_bless_cli_rejects_an_empty_category(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "ghstars.toml"
    monkeypatch.setattr(cli_module, "get_core_config_path", lambda: path)
    monkeypatch.setattr(cli_module, "ensure_config_dir", lambda: tmp_path)

    result = runner.invoke(app, ["taxonomy", "bless", "___"])

    assert result.exit_code != 0
    assert not path.exists()
