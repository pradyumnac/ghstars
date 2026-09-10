import json
from pathlib import Path
from typing import Protocol

import pytest
from pydantic import ValidationError

from ghstars.core.classification import (  # pyright: ignore[reportMissingImports]
    CategoryProposal,
    ClassificationError,
    IntentGuess,
    ProposalRecord,
    ReviewRecord,
    compare_source,
    extract_work,
    load_run_info,
    refresh_work,
    render_markdown,
    write_proposals,
    write_reviews,
)
from ghstars.core.models import List, Star


class StarFactory(Protocol):
    def __call__(self, full_name: str = ..., **overrides: object) -> Star: ...


def proposal(repo: str, top_score: int = 90) -> ProposalRecord:
    return ProposalRecord(
        repo=repo,
        intent=IntentGuess(value="Explore", score=25),
        categories=[
            CategoryProposal(value="Tool", score=top_score),
            CategoryProposal(value="Library", score=60),
            CategoryProposal(value="Example", score=40),
        ],
    )


def test_extract_excludes_archived_and_keeps_current_lists(
    tmp_path: Path, make_star: StarFactory
) -> None:
    active = make_star("zeta/repo", list_ids=["list-1"], language="Python")
    archived = make_star("alpha/old", archived=True)
    lists = [
        List(
            id="list-1",
            name="Explore: Tool",
            slug="explore-tool",
            items=["zeta/repo"],
        )
    ]

    manifest = extract_work([archived, active], lists, tmp_path)

    assert manifest.repos == ["zeta/repo"]
    assert manifest.current["zeta/repo"].lists == ["Explore: Tool"]
    assert (
        json.loads((tmp_path / "classifier-input.jsonl").read_text())["repo"]
        == "zeta/repo"
    )


def test_render_supports_ten_item_review_batches(
    tmp_path: Path, make_star: StarFactory
) -> None:
    stars = [
        make_star(
            f"owner/repo-{index:02d}",
            description=f"Repository {index}",
            language="Python",
        )
        for index in range(12)
    ]
    manifest = extract_work(stars, [], tmp_path)
    write_proposals(
        tmp_path,
        manifest.snapshot,
        [proposal(repo) for repo in manifest.repos],
    )

    output = tmp_path / "batch.md"
    summary = render_markdown(tmp_path, output, 70, offset=10, limit=10)

    assert summary == {
        "items": 2,
        "unclassified": 0,
        "total": 12,
        "offset": 10,
        "limit": 10,
        "next_offset": None,
        "remaining": 0,
    }
    text = output.read_text()
    assert "## 11. owner/repo-10" in text
    assert "**Description:** Repository 10" in text
    assert "**Language:** Python" in text
    assert "## 12. owner/repo-11" in text
    assert "## 10. owner/repo-09" not in text


def test_write_and_render_joins_by_repo_and_marks_low_scores(
    tmp_path: Path, make_star: StarFactory
) -> None:
    star = make_star(
        "owner/repo",
        list_ids=["list-1"],
        description="A useful tool",
        language="Rust",
    )
    lists = [
        List(
            id="list-1",
            name="Explore: Tool",
            slug="explore-tool",
            items=["owner/repo"],
        )
    ]
    manifest = extract_work([star], lists, tmp_path)

    assert (
        write_proposals(tmp_path, manifest.snapshot, [proposal("owner/repo", 69)]) == 1
    )
    output = tmp_path / "classification.md"
    summary = render_markdown(tmp_path, output, 70)

    assert summary == {"items": 1, "unclassified": 1}
    text = output.read_text()
    assert "## 1. owner/repo" in text
    assert "**Description:** A useful tool" in text
    assert "**Language:** Rust" in text
    assert "**Current Lists:** Explore: Tool" in text
    assert "**Target Classifications:** Unclassified" in text
    assert "A. Tool (69)" in text


def test_write_rejects_unknown_repo_and_bad_snapshot(
    tmp_path: Path, make_star: StarFactory
) -> None:
    manifest = extract_work([make_star("owner/repo")], [], tmp_path)

    with pytest.raises(ClassificationError, match="snapshot"):
        write_proposals(tmp_path, "wrong", [proposal("owner/repo")])
    with pytest.raises(ClassificationError, match="unknown repository"):
        write_proposals(tmp_path, manifest.snapshot, [proposal("other/repo")])


def test_write_rejects_conflicting_retry(
    tmp_path: Path, make_star: StarFactory
) -> None:
    manifest = extract_work([make_star("owner/repo")], [], tmp_path)
    write_proposals(tmp_path, manifest.snapshot, [proposal("owner/repo")])
    changed = proposal("owner/repo", 80)

    with pytest.raises(ClassificationError, match="conflicting"):
        write_proposals(tmp_path, manifest.snapshot, [changed])


def test_render_rejects_missing_proposal(
    tmp_path: Path, make_star: StarFactory
) -> None:
    extract_work([make_star("owner/repo")], [], tmp_path)

    with pytest.raises(ClassificationError, match="missing proposals"):
        render_markdown(tmp_path, tmp_path / "out.md", 70)


def test_extract_rejects_unresolved_membership(
    tmp_path: Path, make_star: StarFactory
) -> None:
    star = make_star("owner/repo", list_ids=["missing-list"])

    with pytest.raises(ClassificationError, match="unknown List"):
        extract_work([star], [], tmp_path)


def test_proposal_schema_rejects_extra_fields_and_coerced_scores() -> None:
    with pytest.raises(ValidationError):
        ProposalRecord.model_validate(
            {
                "repo": "owner/repo",
                "explanation": "not allowed",
                "intent": {"value": "Explore", "score": True},
                "categories": [
                    {"value": "Tool", "score": 90},
                    {"value": "Library", "score": 70},
                    {"value": "Example", "score": 40},
                ],
            }
        )


def test_render_rejects_duplicate_and_unknown_persisted_keys(
    tmp_path: Path, make_star: StarFactory
) -> None:
    manifest = extract_work([make_star("owner/repo")], [], tmp_path)
    payload = proposal("owner/repo").model_dump(mode="json")
    line = json.dumps({"snapshot": manifest.snapshot, "proposal": payload})
    (tmp_path / "proposals.jsonl").write_text(f"{line}\n{line}\n")

    with pytest.raises(ClassificationError, match="duplicate proposal"):
        render_markdown(tmp_path, tmp_path / "out.md", 70)

    unknown = proposal("other/repo").model_dump(mode="json")
    (tmp_path / "proposals.jsonl").write_text(
        json.dumps({"snapshot": manifest.snapshot, "proposal": unknown}) + "\n"
    )
    with pytest.raises(ClassificationError, match="unknown proposals"):
        render_markdown(tmp_path, tmp_path / "out.md", 70)


def test_render_rejects_tampered_manifest_contents(
    tmp_path: Path, make_star: StarFactory
) -> None:
    extract_work([make_star("owner/repo")], [], tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    manifest["current"]["owner/repo"]["lists"] = ["Explore: Tampered"]
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))

    with pytest.raises(ClassificationError, match="snapshot"):
        render_markdown(tmp_path, tmp_path / "out.md", 70)


def test_render_rejects_work_file_output_path(
    tmp_path: Path, make_star: StarFactory
) -> None:
    manifest = extract_work([make_star("owner/repo")], [], tmp_path)
    write_proposals(tmp_path, manifest.snapshot, [proposal("owner/repo")])

    with pytest.raises(ClassificationError, match="must not overwrite"):
        render_markdown(tmp_path, tmp_path / "manifest.json", 70)


def test_review_state_is_keyed_by_repo_and_pending_render_keeps_item_numbers(
    tmp_path: Path, make_star: StarFactory
) -> None:
    stars = [make_star(f"owner/repo-{index}") for index in range(3)]
    manifest = extract_work(stars, [], tmp_path)
    write_proposals(
        tmp_path, manifest.snapshot, [proposal(repo) for repo in manifest.repos]
    )
    write_reviews(
        tmp_path,
        manifest.snapshot,
        [
            ReviewRecord(
                repo="owner/repo-0",
                status="selected",
                choice="A",
                intent="Reference",
            )
        ],
    )

    summary = render_markdown(
        tmp_path,
        tmp_path / "pending.md",
        70,
        limit=10,
        pending_only=True,
    )

    assert summary["pending"] == 2
    assert load_run_info(tmp_path).reviewed == 1
    text = (tmp_path / "pending.md").read_text()
    assert "## 1. owner/repo-0" not in text
    assert "## 2. owner/repo-1" in text
    assert "## 3. owner/repo-2" in text


def test_refresh_reuses_only_valid_proposals_and_reviews(
    tmp_path: Path, make_star: StarFactory
) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    old_stars = [
        make_star("owner/changed", description="old"),
        make_star("owner/stable"),
    ]
    manifest = extract_work(old_stars, [], source, classifier="model-a")
    write_proposals(
        source, manifest.snapshot, [proposal(repo) for repo in manifest.repos]
    )
    write_reviews(
        source,
        manifest.snapshot,
        [ReviewRecord(repo="owner/stable", status="skipped")],
    )
    fresh_stars = [
        make_star("owner/changed", description="new"),
        make_star("owner/stable", list_ids=["L1"]),
        make_star("owner/new"),
    ]
    fresh_lists = [
        List(id="L1", name="Explore: Tool", slug="explore-tool", items=["owner/stable"])
    ]

    result = refresh_work(
        source, target, fresh_stars, fresh_lists, classifier="model-a"
    )

    assert result.reused_proposals == 1
    assert result.reused_reviews == 1
    assert result.changes.added == ["owner/new"]
    assert result.changes.classifier_changed == ["owner/changed"]
    assert result.changes.mapping_changed == ["owner/stable"]
    assert load_run_info(source).metadata.state == "superseded"
    assert load_run_info(target).proposals == 1
    assert load_run_info(target).reviewed == 1
    assert compare_source(target, fresh_stars, fresh_lists).changed is False


def test_review_rejects_selection_without_proposal(
    tmp_path: Path, make_star: StarFactory
) -> None:
    manifest = extract_work([make_star("owner/repo")], [], tmp_path)

    with pytest.raises(ClassificationError, match="no accepted proposal"):
        write_reviews(
            tmp_path,
            manifest.snapshot,
            [
                ReviewRecord(
                    repo="owner/repo",
                    status="selected",
                    choice="A",
                    intent="Explore",
                )
            ],
        )


def test_markdown_escapes_classifier_text(
    tmp_path: Path, make_star: StarFactory
) -> None:
    manifest = extract_work([make_star("owner/repo")], [], tmp_path)
    record = ProposalRecord(
        repo="owner/repo",
        intent=IntentGuess(value="Reference", score=10),
        categories=[
            CategoryProposal(value="[x] | `raw`", score=90),
            CategoryProposal(value="Other", score=70),
            CategoryProposal(value="Third", score=40),
        ],
    )
    write_proposals(tmp_path, manifest.snapshot, [record])
    render_markdown(tmp_path, tmp_path / "out.md", 70)
    text = (tmp_path / "out.md").read_text()

    assert "\\[x\\] \\| \\`raw\\`" in text
