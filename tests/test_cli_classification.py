import json
from pathlib import Path
from typing import Protocol

import pytest
from typer.testing import CliRunner

import ghstars.cli as cli_module
from ghstars.cli import app
from ghstars.core.classification import (
    ProposalRecord,
    extract_work,
    load_run_info,
    supersede_run,
    write_proposals,
)
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


def test_classify_extract_defaults_to_persistent_data_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("GHSTARS_HOME", str(home))
    store = StateStore(home / "state")
    store.save_stars([make_star("owner/repo")])
    _use_store(monkeypatch, store)

    result = runner.invoke(app, ["classify", "extract", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    work = Path(payload["resume_path"])
    assert work.parent == home / "data" / "classify"
    assert work == Path(payload["work_dir"])
    assert (work / "manifest.json").exists()


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


def test_explicit_work_dir_does_not_supersede_managed_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("GHSTARS_HOME", str(home))
    star = make_star("owner/repo")
    store = StateStore(tmp_path / "component-state")
    store.save_stars([star])
    _use_store(monkeypatch, store)
    managed = home / "data" / "classify" / "managed"
    extract_work([star], [], managed)

    result = runner.invoke(
        app,
        [
            "classify",
            "extract",
            "--work-dir",
            str(tmp_path / "component-work"),
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert load_run_info(managed).metadata.state == "classifying"
    assert load_run_info(managed).metadata.superseded_by is None


def test_classify_extract_reports_invalid_utf8_as_json_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StateStore(tmp_path / "state")
    (store.base_dir / "stars.json").write_bytes(b"\xff")
    _use_store(monkeypatch, store)

    result = runner.invoke(
        app,
        ["classify", "extract", "--work-dir", str(tmp_path / "work"), "--json"],
    )

    assert result.exit_code == 1
    assert '"error"' in result.output
    assert "Traceback" not in result.output


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


def _proposal(repo: str) -> ProposalRecord:
    return ProposalRecord.model_validate(
        {
            "repo": repo,
            "intent": {"value": "Explore", "score": 20},
            "categories": [
                {"value": "Tool", "score": 90},
                {"value": "Library", "score": 70},
                {"value": "Example", "score": 40},
            ],
        }
    )


def test_classify_extract_resumes_matching_run_with_most_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("GHSTARS_HOME", str(home))
    store = StateStore(home / "state")
    star = make_star("owner/repo")
    store.save_stars([star])
    _use_store(monkeypatch, store)
    root = home / "data" / "classify"
    empty = root / "empty"
    progressed = root / "progressed"
    extract_work([star], [], empty)
    manifest = extract_work([star], [], progressed)
    write_proposals(progressed, manifest.snapshot, [_proposal("owner/repo")])

    result = runner.invoke(app, ["classify", "extract", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["action"] == "resume"
    assert payload["resume_path"] == str(progressed)
    assert payload["proposals"] == 1


def test_classify_extract_new_supersedes_active_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("GHSTARS_HOME", str(home))
    store = StateStore(home / "state")
    star = make_star("owner/repo")
    store.save_stars([star])
    _use_store(monkeypatch, store)
    old = home / "data" / "classify" / "old"
    extract_work([star], [], old)

    result = runner.invoke(app, ["classify", "extract", "--new", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["action"] == "new"
    assert Path(payload["resume_path"]) != old
    assert load_run_info(old).metadata.state == "superseded"


def test_classify_extract_resuming_superseded_run_creates_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("GHSTARS_HOME", str(home))
    store = StateStore(home / "state")
    star = make_star("owner/repo")
    store.save_stars([star])
    _use_store(monkeypatch, store)
    old = home / "data" / "classify" / "old"
    replacement = home / "data" / "classify" / "replacement"
    extract_work([star], [], old)
    extract_work([star], [], replacement)
    supersede_run(old, replacement)

    result = runner.invoke(app, ["classify", "extract", "--resume", str(old), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["action"] == "refresh"
    assert Path(payload["resume_path"]) not in (old, replacement)
    assert load_run_info(old).metadata.state == "superseded"


def test_classify_extract_refreshes_changed_source_and_reuses_stable_proposal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("GHSTARS_HOME", str(home))
    store = StateStore(home / "state")
    old_stars = [
        make_star("owner/changed", description="old"),
        make_star("owner/stable"),
    ]
    store.save_stars(old_stars)
    _use_store(monkeypatch, store)
    old = home / "data" / "classify" / "old"
    manifest = extract_work(old_stars, [], old)
    write_proposals(
        old, manifest.snapshot, [_proposal(repo) for repo in manifest.repos]
    )
    store.save_stars(
        [
            make_star("owner/changed", description="new"),
            make_star("owner/stable"),
        ]
    )

    result = runner.invoke(app, ["classify", "extract", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["action"] == "refresh"
    assert payload["reused_proposals"] == 1
    assert payload["pending_proposals"] == 1
    assert payload["changes"]["classifier_changed"] == ["owner/changed"]


def test_classify_review_persists_selection_and_pending_render_skips_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path / "state")
    star = make_star("owner/repo")
    store.save_stars([star])
    _use_store(monkeypatch, store)
    work = tmp_path / "work"
    manifest = extract_work([star], [], work)
    write_proposals(work, manifest.snapshot, [_proposal("owner/repo")])
    decisions = tmp_path / "reviews.jsonl"
    decisions.write_text(
        json.dumps(
            {
                "repo": "owner/repo",
                "status": "selected",
                "choice": "A",
                "intent": "Reference",
            }
        )
        + "\n"
    )

    reviewed = runner.invoke(
        app,
        [
            "classify",
            "review",
            "--work-dir",
            str(work),
            "--snapshot",
            manifest.snapshot,
            "--input",
            str(decisions),
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
            str(tmp_path / "pending.md"),
            "--pending",
            "--limit",
            "10",
            "--json",
        ],
    )

    assert reviewed.exit_code == 0
    assert json.loads(reviewed.output)["state"] == "complete"
    assert rendered.exit_code == 0
    assert json.loads(rendered.output)["rows"] == 0


def test_classify_check_reports_local_source_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path / "state")
    star = make_star("owner/repo", description="old")
    store.save_stars([star])
    _use_store(monkeypatch, store)
    work = tmp_path / "work"
    extract_work([star], [], work)

    current = runner.invoke(
        app, ["classify", "check", "--work-dir", str(work), "--json"]
    )
    store.save_stars([make_star("owner/repo", description="new")])
    stale = runner.invoke(app, ["classify", "check", "--work-dir", str(work), "--json"])

    assert json.loads(current.output)["state"] == "current"
    stale_payload = json.loads(stale.output)
    assert stale_payload["state"] == "stale"
    assert stale_payload["changes"]["classifier_changed"] == ["owner/repo"]


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
