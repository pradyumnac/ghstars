"""Tests for `ghstars.cli.deps.get_ghstars_home` (ticket 30)."""

from pathlib import Path

import pytest

from ghstars.cli import deps as deps_module


def test_get_ghstars_home_defaults_when_env_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(deps_module, "DEFAULT_GHSTARS_HOME", tmp_path)

    assert deps_module.get_ghstars_home() == tmp_path


def test_get_ghstars_home_honors_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    override = tmp_path / "isolated-home"
    monkeypatch.setenv("GHSTARS_HOME", str(override))

    assert deps_module.get_ghstars_home() == override


def test_get_store_uses_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    override = tmp_path / "isolated-home"
    monkeypatch.setenv("GHSTARS_HOME", str(override))

    store = deps_module.get_store()

    assert store.base_dir == override / "state"
