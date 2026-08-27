"""Tests for the core-tier config file, `~/.ghstars/config/ghstars.toml`
(ticket 32): `load_core_config`, its `[export]` table, and the path
getters in `ghstars.cli.deps`.
"""

from pathlib import Path

import pytest

import ghstars.cli.deps as deps_module
from ghstars.core.config import CoreConfig, CoreConfigError, load_core_config
from ghstars.core.export import ExportConfig

# --- load_core_config ---------------------------------------------------


def test_load_core_config_missing_file_is_empty_config(tmp_path: Path) -> None:
    config = load_core_config(tmp_path / "ghstars.toml")

    assert config == CoreConfig()
    assert config.export == ExportConfig()


def test_load_core_config_invalid_toml_raises(tmp_path: Path) -> None:
    path = tmp_path / "ghstars.toml"
    path.write_text("this is not [valid toml")

    with pytest.raises(CoreConfigError):
        load_core_config(path)


def test_load_core_config_parses_export_table(tmp_path: Path) -> None:
    path = tmp_path / "ghstars.toml"
    path.write_text(
        """
[[export.exports]]
name = "tools"
list_name = "Current: Vendored Skills"
output = "tools.yaml"
format = "yaml"

[[export.exports]]
name = "tools-under-exploration"
category = "Vendored Skills"
intent = "Explore"
output = "tools-under-exploration.yaml"
format = "yaml"
"""
    )

    config = load_core_config(path)

    assert len(config.export.exports) == 2
    assert config.export.exports[0].list_name == "Current: Vendored Skills"
    assert config.export.exports[1].category == "Vendored Skills"
    assert config.export.exports[1].intent == "Explore"


@pytest.mark.parametrize(
    "entry",
    [
        # neither list nor category
        {"name": "x", "output": "x.yaml", "format": "yaml"},
        # both list and category
        {
            "name": "x",
            "list_name": "Explore: X",
            "category": "X",
            "output": "x.yaml",
            "format": "yaml",
        },
        # intent alongside list, not category
        {
            "name": "x",
            "list_name": "Explore: X",
            "intent": "Explore",
            "output": "x.yaml",
            "format": "yaml",
        },
        # unknown Star field
        {
            "name": "x",
            "list_name": "Explore: X",
            "output": "x.yaml",
            "format": "yaml",
            "fields": ["not_a_real_field"],
        },
    ],
)
def test_load_core_config_rejects_invalid_export_entries(
    tmp_path: Path, entry: dict[str, object]
) -> None:
    path = tmp_path / "ghstars.toml"
    # Build minimal TOML directly from each entry.
    lines = ["[[export.exports]]"]
    for key, value in entry.items():
        if isinstance(value, list):
            rendered = "[" + ", ".join(f'"{v}"' for v in value) + "]"
        else:
            rendered = f'"{value}"'
        lines.append(f"{key} = {rendered}")
    path.write_text("\n".join(lines))

    with pytest.raises(CoreConfigError):
        load_core_config(path)


def test_load_core_config_rejects_unknown_top_level_table(tmp_path: Path) -> None:
    """`CoreConfig` only defines `export` today; an unrelated table is a
    typo, not a future extension point -- `model_config = ConfigDict(
    extra="forbid")` surfaces it at load time rather than silently
    dropping it (same rule `TuiConfig` follows).
    """
    path = tmp_path / "ghstars.toml"
    path.write_text('exports = ["not", "a", "table"]\n')

    with pytest.raises(CoreConfigError):
        load_core_config(path)


# --- leftover export.toml ------------------------------------------------


def test_check_stale_export_config_warns_once_when_file_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(deps_module, "DEFAULT_GHSTARS_HOME", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "export.toml").write_text("[[exports]]\n")

    deps_module.check_stale_export_config()

    captured = capsys.readouterr()
    assert "export.toml" in captured.err
    assert "no longer read" in captured.err


def test_check_stale_export_config_silent_when_file_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(deps_module, "DEFAULT_GHSTARS_HOME", tmp_path)

    deps_module.check_stale_export_config()

    captured = capsys.readouterr()
    assert captured.err == ""


# --- path getters ----------------------------------------------------------


def test_get_core_config_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(deps_module, "DEFAULT_GHSTARS_HOME", tmp_path)

    assert deps_module.get_core_config_path() == tmp_path / "config" / "ghstars.toml"


def test_get_cli_config_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(deps_module, "DEFAULT_GHSTARS_HOME", tmp_path)

    assert deps_module.get_cli_config_path() == tmp_path / "config" / "cli.toml"


def test_get_tui_config_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(deps_module, "DEFAULT_GHSTARS_HOME", tmp_path)

    assert deps_module.get_tui_config_path() == tmp_path / "config" / "tui.toml"
