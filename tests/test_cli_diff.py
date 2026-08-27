"""Tests for `ghstars diff` (ticket 11).

`ghstars diff` is a thin wrapper around the user's own `git diff`/`git log
-p` against `state/` -- it never runs `git init` and never commits to
`state/` itself (ADR 0002). These tests exercise the real `git` binary
against a throwaway repo under `tmp_path`, since there is no bespoke diff
engine to fake out.
"""

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

import ghstars.cli as cli_module
from ghstars.cli import app
from ghstars.core.state_store import StateStore

runner = CliRunner()


def _use_store(monkeypatch: pytest.MonkeyPatch, store: StateStore) -> None:
    monkeypatch.setattr(cli_module, "get_store", lambda: store)
    monkeypatch.setattr(cli_module, "ensure_config_dir", lambda: store.base_dir)


def _git(state_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-C", str(state_dir), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result


def _init_git_repo(state_dir: Path) -> None:
    """A throwaway repo simulating the user tracking `state/` themselves."""
    _git(state_dir, "init", "-q")
    _git(state_dir, "config", "user.email", "test@example.com")
    _git(state_dir, "config", "user.name", "Test")
    _git(state_dir, "config", "commit.gpgsign", "false")


def test_diff_reports_no_git_history_when_state_is_not_git_tracked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path / "state")
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["diff"])

    assert result.exit_code == 1
    assert "no git history available" in result.output
    assert not (store.base_dir / ".git").exists()


def test_diff_never_runs_git_init_on_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path / "state")
    _use_store(monkeypatch, store)

    runner.invoke(app, ["diff"])
    runner.invoke(app, ["diff", "--log"])

    assert not (store.base_dir / ".git").exists()


def test_diff_shows_a_summary_by_default_when_state_is_git_tracked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path / "state")
    _init_git_repo(store.base_dir)
    (store.base_dir / "stars.json").write_text('[{"full_name": "a/b"}]')
    _git(store.base_dir, "add", "stars.json")
    _git(store.base_dir, "commit", "-q", "-m", "initial classification")
    (store.base_dir / "stars.json").write_text('[{"full_name": "a/b-renamed"}]')
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["diff"])

    assert result.exit_code == 0
    assert "stars.json" in result.output
    assert "1 file changed" in result.output
    assert "a/b-renamed" not in result.output


def test_diff_reports_no_changes_as_empty_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path / "state")
    _init_git_repo(store.base_dir)
    (store.base_dir / "stars.json").write_text('[{"full_name": "a/b"}]')
    _git(store.base_dir, "add", "stars.json")
    _git(store.base_dir, "commit", "-q", "-m", "initial classification")
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["diff"])

    assert result.exit_code == 0
    assert result.output == ""


def test_diff_patch_shows_the_full_patch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path / "state")
    _init_git_repo(store.base_dir)
    (store.base_dir / "stars.json").write_text('[{"full_name": "a/b"}]')
    _git(store.base_dir, "add", "stars.json")
    _git(store.base_dir, "commit", "-q", "-m", "initial classification")
    (store.base_dir / "stars.json").write_text('[{"full_name": "a/b-renamed"}]')
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["diff", "--patch"])

    assert result.exit_code == 0
    assert "a/b-renamed" in result.output
    assert "-a/b" in result.output or "a/b" in result.output


def test_diff_log_shows_commit_history_with_patch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path / "state")
    _init_git_repo(store.base_dir)
    (store.base_dir / "stars.json").write_text('[{"full_name": "a/b"}]')
    _git(store.base_dir, "add", "stars.json")
    _git(store.base_dir, "commit", "-q", "-m", "initial classification")
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["diff", "--log"])

    assert result.exit_code == 0
    assert "initial classification" in result.output
    assert "a/b" in result.output


def test_diff_never_creates_a_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path / "state")
    _init_git_repo(store.base_dir)
    (store.base_dir / "stars.json").write_text('[{"full_name": "a/b"}]')
    _git(store.base_dir, "add", "stars.json")
    _git(store.base_dir, "commit", "-q", "-m", "initial classification")
    (store.base_dir / "stars.json").write_text('[{"full_name": "a/b-renamed"}]')
    _use_store(monkeypatch, store)

    runner.invoke(app, ["diff"])
    runner.invoke(app, ["diff", "--log"])

    log = _git(store.base_dir, "log", "--oneline")
    assert log.stdout.count("\n") == 1
    status = _git(store.base_dir, "status", "--porcelain")
    assert "M stars.json" in status.stdout


def test_diff_passes_extra_args_through_to_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path / "state")
    _init_git_repo(store.base_dir)
    (store.base_dir / "stars.json").write_text('[{"full_name": "a/b"}]')
    _git(store.base_dir, "add", "stars.json")
    _git(store.base_dir, "commit", "-q", "-m", "initial classification")
    (store.base_dir / "stars.json").write_text('[{"full_name": "a/b-renamed"}]')
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["diff", "--patch", "--numstat"])

    assert result.exit_code == 0
    assert "stars.json" in result.output
    assert "a/b-renamed" not in result.output


def test_diff_reports_git_not_installed_without_crashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path / "state")
    _use_store(monkeypatch, store)

    def _raise_missing_git(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("git")

    # Patch the shared subprocess module used by the code under test.
    monkeypatch.setattr(subprocess, "run", _raise_missing_git)

    result = runner.invoke(app, ["diff"])

    assert result.exit_code == 1
    assert "git is not installed" in result.output


def test_diff_reports_git_disappearing_mid_command_without_crashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`git_unavailable_reason` succeeds (git found), but git becomes
    unavailable before the actual `diff`/`log` call -- e.g. removed from
    PATH between the two subprocess calls. Must still fail cleanly via
    `fail()`, not with a raw traceback (code-review finding).
    """
    store = StateStore(tmp_path / "state")
    _use_store(monkeypatch, store)
    # Simulate the availability check having already passed.
    monkeypatch.setattr(cli_module, "git_unavailable_reason", lambda _dir: None)

    def _raise_missing_git(
        *_args: object, **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", _raise_missing_git)

    result = runner.invoke(app, ["diff"])

    assert result.exit_code == 1
    assert "git is not installed" in result.output


def test_diff_scopes_to_state_dir_when_the_repo_is_rooted_above_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression test (code-review finding): when the user tracks all of
    `~/.ghstars/` (or similar) from one repo rooted above `state/`, `ghstars
    diff` must show only changes under `state/` -- not unrelated changes
    elsewhere in the same repo, e.g. `config/secrets.yaml`.
    """
    root = tmp_path
    _init_git_repo(root)
    (root / "state").mkdir()
    (root / "config").mkdir()
    (root / "state" / "stars.json").write_text('[{"full_name": "a/b"}]')
    (root / "config" / "secrets.yaml").write_text("token: initial\n")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "initial")
    (root / "state" / "stars.json").write_text('[{"full_name": "a/b-renamed"}]')
    (root / "config" / "secrets.yaml").write_text("token: rotated\n")

    store = StateStore(root / "state")
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["diff", "--patch"])

    assert result.exit_code == 0
    assert "stars.json" in result.output
    assert "a/b-renamed" in result.output
    assert "secrets.yaml" not in result.output
    assert "rotated" not in result.output
