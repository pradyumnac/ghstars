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
    extract_work,
    render_markdown,
    write_proposals,
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


def test_write_and_render_joins_by_repo_and_marks_low_scores(
    tmp_path: Path, make_star: StarFactory
) -> None:
    star = make_star("owner/repo", list_ids=["list-1"])
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

    assert summary == {"rows": 1, "unclassified": 1}
    text = output.read_text()
    assert "1. owner/repo" in text
    assert "Explore: Tool" in text
    assert "Unclassified" in text
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
