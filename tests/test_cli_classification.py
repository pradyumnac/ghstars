import json
from pathlib import Path
from typing import Protocol

import pytest
from typer.testing import CliRunner

import ghstars.cli as cli_module
from ghstars.cli import app
from ghstars.core.models import List, Star
from ghstars.core.state_store import StateStore

runner = CliRunner()


class StarFactory(Protocol):
    def __call__(self, full_name: str = ..., **overrides: object) -> Star: ...


def _use_store(monkeypatch: pytest.MonkeyPatch, store: StateStore) -> None:
    monkeypatch.setattr(cli_module, "get_read_only_store", lambda: store)
    monkeypatch.setattr(cli_module, "get_store", lambda: store)
    monkeypatch.setattr(cli_module, "ensure_config_dir", lambda: store.base_dir)


def test_classify_extract_does_not_create_state_or_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("GHSTARS_HOME", str(home))

    result = runner.invoke(
        app,
        [
            "classify",
            "extract",
            "--work-dir",
            str(tmp_path / "work"),
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert not (home / "config").exists()
    assert not (home / "state").exists()


def test_classify_extract_is_offline_and_writes_runtime_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path / "state")
    store.save_stars([make_star("owner/repo", language="Python")])
    store.save_lists([List(id="L1", name="Explore: Tool", slug="explore-tool")])
    _use_store(monkeypatch, store)
    work = tmp_path / "work"

    result = runner.invoke(
        app, ["classify", "extract", "--work-dir", str(work), "--json"]
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["count"] == 1
    assert (work / "manifest.json").exists()
    assert (
        json.loads((work / "classifier-input.jsonl").read_text())["repo"]
        == "owner/repo"
    )


def test_classify_extract_reports_corrupt_state_as_json_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path / "state")
    (store.base_dir / "stars.json").write_text("{not valid json")
    _use_store(monkeypatch, store)

    result = runner.invoke(
        app,
        ["classify", "extract", "--work-dir", str(tmp_path / "work"), "--json"],
    )

    assert result.exit_code == 1
    assert '"error"' in result.output
    assert "Traceback" not in result.output


def test_classify_write_and_render_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path / "state")
    store.save_stars([make_star("owner/repo")])
    _use_store(monkeypatch, store)
    work = tmp_path / "work"
    extracted = runner.invoke(
        app, ["classify", "extract", "--work-dir", str(work), "--json"]
    )
    snapshot = json.loads(extracted.output)["snapshot"]
    proposals = tmp_path / "proposals.jsonl"
    proposals.write_text(
        json.dumps(
            {
                "repo": "owner/repo",
                "intent": {"value": "Reference", "score": 20},
                "categories": [
                    {"value": "Tool", "score": 90},
                    {"value": "Library", "score": 70},
                    {"value": "Example", "score": 40},
                ],
            }
        )
        + "\n"
    )

    written = runner.invoke(
        app,
        [
            "classify",
            "write",
            "--work-dir",
            str(work),
            "--snapshot",
            snapshot,
            "--input",
            str(proposals),
            "--json",
        ],
    )
    rendered = runner.invoke(
        app,
        [
            "classify",
            "render",
            "--work-dir",
            str(work),
            "--output",
            str(tmp_path / "classification.md"),
            "--json",
        ],
    )

    assert written.exit_code == 0
    assert json.loads(written.output)["accepted"] == 1
    assert rendered.exit_code == 0
    assert json.loads(rendered.output)["rows"] == 1
    assert "| 1. owner/repo |" in (tmp_path / "classification.md").read_text()
