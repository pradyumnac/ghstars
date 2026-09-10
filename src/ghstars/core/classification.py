"""Offline classification-debt extraction and reconciliation."""

from __future__ import annotations

import hashlib
import html
import json
from collections.abc import Sequence
from itertools import pairwise
from pathlib import Path

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    ValidationError,
    field_validator,
)

from ghstars.core.state_store import atomic_write

JsonObject = dict[str, object]

from ghstars.core.models import Intent, List, Star
from ghstars.core.taxonomy import classify_list, normalize_category


class ClassificationError(ValueError):
    """The classification work directory or input has an invalid shape."""


class ClassifierRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repo: str
    description: str | None = None
    language: str | None = None
    fork: bool = False
    follow: bool = False


class IntentGuess(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Intent
    score: StrictInt

    @field_validator("score")
    @classmethod
    def score_range(cls, value: int) -> int:
        if not 0 <= value <= 100:
            raise ValueError("score must be between 0 and 100")
        return value


class CategoryProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    score: StrictInt

    @field_validator("value")
    @classmethod
    def non_empty_value(cls, value: str) -> str:
        if not normalize_category(value):
            raise ValueError("category must not be empty")
        return value

    @field_validator("score")
    @classmethod
    def score_range(cls, value: int) -> int:
        if not 0 <= value <= 100:
            raise ValueError("score must be between 0 and 100")
        return value


class ProposalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repo: str
    intent: IntentGuess
    categories: list[CategoryProposal]

    @field_validator("categories")
    @classmethod
    def exactly_three_distinct(
        cls, value: list[CategoryProposal]
    ) -> list[CategoryProposal]:
        if len(value) != 3:
            raise ValueError("categories must contain exactly three proposals")
        keys = [normalize_category(item.value).casefold() for item in value]
        if len(set(keys)) != 3:
            raise ValueError("categories must be distinct")
        if any(left.score < right.score for left, right in pairwise(value)):
            raise ValueError("categories must be sorted by descending score")
        return value


class CurrentMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lists: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot: str
    repos: list[str]
    current: dict[str, CurrentMapping]


class StoredWork(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest: Manifest
    classifier_input: list[ClassifierRecord]


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _snapshot_content(
    repos: list[str],
    records: list[ClassifierRecord],
    current: dict[str, CurrentMapping],
) -> str:
    payload = {
        "repos": repos,
        "classifier_input": [item.model_dump(mode="json") for item in records],
        "current": {repo: current[repo].model_dump(mode="json") for repo in repos},
    }
    return hashlib.sha256(_canonical(payload).encode()).hexdigest()


def extract_work(stars: list[Star], lists: list[List], work_dir: Path) -> Manifest:
    """Write one stable, offline classification snapshot."""
    active = sorted(
        (star for star in stars if not star.archived), key=lambda s: s.full_name
    )
    classified_lists = [classify_list(item) for item in lists]
    _validate_inputs(active, classified_lists)
    by_id = {item.id: item for item in classified_lists}
    current: dict[str, CurrentMapping] = {}
    classifier_input: list[ClassifierRecord] = []
    for star in active:
        memberships = [by_id[item] for item in star.list_ids if item in by_id]
        current[star.full_name] = CurrentMapping(
            lists=[item.name for item in memberships],
            categories=[item.category for item in memberships if item.category],
        )
        classifier_input.append(
            ClassifierRecord(
                repo=star.full_name,
                description=star.description,
                language=star.language,
                fork=star.fork,
                follow=star.follow,
            )
        )

    repos = [item.full_name for item in active]
    manifest = Manifest(
        snapshot=_snapshot_content(repos, classifier_input, current),
        repos=repos,
        current=current,
    )
    work_dir.mkdir(parents=True, exist_ok=True)
    _write_json(work_dir / "manifest.json", manifest.model_dump(mode="json"))
    _write_raw_jsonl(work_dir / "classifier-input.jsonl", classifier_input)
    return manifest


def load_work(work_dir: Path) -> StoredWork:
    try:
        manifest = Manifest.model_validate(_read_json(work_dir / "manifest.json"))
        records = [
            ClassifierRecord.model_validate(item)
            for item in _read_jsonl(work_dir / "classifier-input.jsonl")
        ]
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise ClassificationError(
            f"invalid classification work directory: {exc}"
        ) from exc
    if [item.repo for item in records] != manifest.repos:
        raise ClassificationError(
            "classifier input does not match manifest repositories"
        )
    if set(manifest.current) != set(manifest.repos):
        raise ClassificationError(
            "current mapping does not match manifest repositories"
        )
    expected = _snapshot_content(manifest.repos, records, manifest.current)
    if manifest.snapshot != expected:
        raise ClassificationError("manifest snapshot does not match work contents")
    return StoredWork(manifest=manifest, classifier_input=records)


def write_proposals(
    work_dir: Path, snapshot: str, records: list[ProposalRecord]
) -> int:
    """Validate and idempotently append a classifier batch."""
    work = load_work(work_dir)
    if snapshot != work.manifest.snapshot:
        raise ClassificationError("snapshot does not match manifest")
    existing = {
        item.repo: item
        for item in _load_proposals(work_dir, expected_snapshot=work.manifest.snapshot)
    }
    valid_repos = set(work.manifest.repos)
    for record in records:
        if record.repo not in valid_repos:
            raise ClassificationError(
                f"proposal has unknown repository {record.repo!r}"
            )
        prior = existing.get(record.repo)
        if prior is not None and prior.model_dump() != record.model_dump():
            raise ClassificationError(f"conflicting proposal for {record.repo!r}")
        existing[record.repo] = record
    payload = [existing[repo] for repo in work.manifest.repos if repo in existing]
    _write_jsonl(work_dir / "proposals.jsonl", payload, extra={"snapshot": snapshot})
    return len(records)


def render_markdown(work_dir: Path, output: Path, threshold: int) -> dict[str, int]:
    """Join validated proposals with current mappings and write Markdown."""
    if not 0 <= threshold <= 100:
        raise ClassificationError("threshold must be between 0 and 100")
    work = load_work(work_dir)
    proposals = _load_proposals(work_dir, expected_snapshot=work.manifest.snapshot)
    proposal_repos = [item.repo for item in proposals]
    expected_repos = set(work.manifest.repos)
    actual_repos = set(proposal_repos)
    missing = sorted(expected_repos - actual_repos)
    unknown = sorted(actual_repos - expected_repos)
    if missing or unknown or len(proposal_repos) != len(expected_repos):
        details = []
        if missing:
            details.append(f"missing proposals for: {', '.join(missing)}")
        if unknown:
            details.append(f"unknown proposals for: {', '.join(unknown)}")
        raise ClassificationError(
            "; ".join(details) or "proposal keys do not match manifest"
        )
    by_repo = {item.repo: item for item in proposals}
    rows: list[str] = [
        "| Repository | Current Lists | Target Classifications |",
        "| --- | --- | --- |",
    ]
    unclassified = 0
    for index, repo in enumerate(work.manifest.repos, 1):
        record = by_repo[repo]
        mapping = work.manifest.current[record.repo]
        current = "; ".join(mapping.lists) or "—"
        intent = f"Intent guess: {record.intent.value} ({record.intent.score})"
        choices = "; ".join(
            f"{letter}. {item.value} ({item.score})"
            for letter, item in zip(("A", "B", "C"), record.categories, strict=True)
        )
        if record.categories[0].score < threshold:
            unclassified += 1
            target = f"Unclassified; {intent}; {choices}"
        else:
            target = f"{intent}; {choices}"
        rows.append(f"| {index}. {_md(record.repo)} | {_md(current)} | {_md(target)} |")
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(output, "\n".join(rows) + "\n")
    return {"rows": len(proposals), "unclassified": unclassified}


def _load_proposals(
    work_dir: Path, *, expected_snapshot: str | None = None
) -> list[ProposalRecord]:
    path = work_dir / "proposals.jsonl"
    if not path.exists():
        return []
    try:
        envelope = _read_jsonl(path)
        result: list[ProposalRecord] = []
        seen: set[str] = set()
        for item in envelope:
            if (
                expected_snapshot is not None
                and item.get("snapshot") != expected_snapshot
            ):
                raise ClassificationError("proposal snapshot does not match manifest")
            payload = item.get("proposal", item)
            proposal = ProposalRecord.model_validate(payload)
            if proposal.repo in seen:
                raise ClassificationError(f"duplicate proposal for {proposal.repo!r}")
            seen.add(proposal.repo)
            result.append(proposal)
        return result
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise ClassificationError(f"invalid proposals file: {exc}") from exc


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ClassificationError(f"cannot read {path}: {exc}") from exc


def _read_jsonl(path: Path) -> list[JsonObject]:
    try:
        values = [
            json.loads(line) for line in path.read_text().splitlines() if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise ClassificationError(f"cannot read {path}: {exc}") from exc
    if not all(isinstance(value, dict) for value in values):
        raise ClassificationError(f"{path} must contain JSON objects")
    return [value for value in values if isinstance(value, dict)]


def _write_json(path: Path, value: object) -> None:
    atomic_write(path, json.dumps(value, indent=2) + "\n")


def _write_raw_jsonl(path: Path, records: Sequence[BaseModel]) -> None:
    content = "\n".join(
        json.dumps(record.model_dump(mode="json"), separators=(",", ":"))
        for record in records
    )
    atomic_write(path, content + ("\n" if records else ""))


def _write_jsonl(
    path: Path, records: Sequence[BaseModel], extra: dict[str, str] | None = None
) -> None:
    lines: list[str] = []
    for record in records:
        item: JsonObject = {"proposal": record.model_dump(mode="json")}
        if extra:
            item.update(extra)
        lines.append(json.dumps(item, separators=(",", ":")))
    atomic_write(path, "\n".join(lines) + ("\n" if lines else ""))


def _validate_inputs(stars: list[Star], lists: list[List]) -> None:
    star_names = [star.full_name for star in stars]
    if len(star_names) != len(set(star_names)):
        raise ClassificationError("duplicate Star.full_name in local state")
    list_ids = [item.id for item in lists]
    if len(list_ids) != len(set(list_ids)):
        raise ClassificationError("duplicate List.id in local state")
    by_id = {item.id: item for item in lists}
    active_names = set(star_names)
    for star in stars:
        missing = sorted(item for item in star.list_ids if item not in by_id)
        if missing:
            raise ClassificationError(
                f"{star.full_name}: unknown List id(s): {', '.join(missing)}"
            )
        for list_id in star.list_ids:
            if star.full_name not in by_id[list_id].items:
                raise ClassificationError(
                    f"{star.full_name}: List {by_id[list_id].name!r} does not include it"
                )
    for item in lists:
        for repo in item.items:
            if repo in active_names and item.id not in next(
                star.list_ids for star in stars if star.full_name == repo
            ):
                raise ClassificationError(
                    f"{repo}: List {item.name!r} claims it without Star membership"
                )


def _md(value: str) -> str:
    escaped = html.escape(value.replace("\\", "\\\\"), quote=False)
    for marker in ("|", "`", "[", "]", "*", "_"):
        escaped = escaped.replace(marker, f"\\{marker}")
    return escaped.replace("\n", "<br>").replace("\r", "")
