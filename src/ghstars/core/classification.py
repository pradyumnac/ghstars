"""Offline classification-debt extraction and reconciliation."""

from __future__ import annotations

import hashlib
import html
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Literal

from filelock import FileLock
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


RunState = Literal["classifying", "reviewing", "complete", "superseded"]
ReviewStatus = Literal["selected", "skipped"]
ReviewChoice = Literal["A", "B", "C"]


class RunMetadata(BaseModel):
    """Persistent identity and lineage for one classification snapshot."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    created_at: datetime
    updated_at: datetime
    state: RunState
    snapshot: str
    classifier: str = "unspecified"
    prompt_version: Literal[1] = 1
    parent_run: str | None = None
    superseded_by: str | None = None


class ReviewRecord(BaseModel):
    """One repository-keyed user decision."""

    model_config = ConfigDict(extra="forbid")

    repo: str
    status: ReviewStatus
    choice: ReviewChoice | None = None
    intent: Intent | None = None


class SourceChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    classifier_changed: list[str] = Field(default_factory=list)
    mapping_changed: list[str] = Field(default_factory=list)

    @property
    def changed(self) -> bool:
        return any(
            (self.added, self.removed, self.classifier_changed, self.mapping_changed)
        )


class RunInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: Path
    metadata: RunMetadata
    proposals: int
    reviewed: int
    total: int


class RefreshResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest: Manifest
    reused_proposals: int
    reused_reviews: int
    changes: SourceChanges


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


def build_work(stars: list[Star], lists: list[List]) -> StoredWork:
    """Build one validated classification snapshot without writing it."""
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
    return StoredWork(manifest=manifest, classifier_input=classifier_input)


def extract_work(
    stars: list[Star],
    lists: list[List],
    work_dir: Path,
    *,
    classifier: str = "unspecified",
    parent_run: str | None = None,
) -> Manifest:
    """Write one stable, offline classification snapshot."""
    work = build_work(stars, lists)
    now = datetime.now(UTC)
    metadata = RunMetadata(
        created_at=now,
        updated_at=now,
        state="classifying" if work.manifest.repos else "complete",
        snapshot=work.manifest.snapshot,
        classifier=classifier,
        parent_run=parent_run,
    )
    work_dir.mkdir(parents=True, exist_ok=True)
    with FileLock(str(work_dir / ".lock")).acquire(timeout=5.0):
        _write_json(work_dir / "manifest.json", work.manifest.model_dump(mode="json"))
        _write_raw_jsonl(work_dir / "classifier-input.jsonl", work.classifier_input)
        _write_json(work_dir / "run.json", metadata.model_dump(mode="json"))
        (work_dir / "proposals.jsonl").unlink(missing_ok=True)
        (work_dir / "reviews.jsonl").unlink(missing_ok=True)
    return work.manifest


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
    with FileLock(str(work_dir / ".lock")).acquire(timeout=5.0):
        work = load_work(work_dir)
        if snapshot != work.manifest.snapshot:
            raise ClassificationError("snapshot does not match manifest")
        existing = {
            item.repo: item
            for item in _load_proposals(
                work_dir, expected_snapshot=work.manifest.snapshot
            )
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
        _write_jsonl(
            work_dir / "proposals.jsonl", payload, extra={"snapshot": snapshot}
        )
        _write_run_state_locked(work_dir, work, len(payload))
        return len(records)


def write_reviews(work_dir: Path, snapshot: str, records: list[ReviewRecord]) -> int:
    """Validate and store repository-keyed review decisions."""
    with FileLock(str(work_dir / ".lock")).acquire(timeout=5.0):
        work = load_work(work_dir)
        if snapshot != work.manifest.snapshot:
            raise ClassificationError("snapshot does not match manifest")
        proposals = {
            item.repo: item
            for item in _load_proposals(
                work_dir, expected_snapshot=work.manifest.snapshot
            )
        }
        existing = {
            item.repo: item
            for item in _load_reviews(
                work_dir,
                expected_snapshot=work.manifest.snapshot,
                proposals=proposals,
            )
        }
        for record in records:
            _validate_review(record, proposals)
            existing[record.repo] = record
        payload = [existing[repo] for repo in work.manifest.repos if repo in existing]
        _write_review_jsonl(work_dir / "reviews.jsonl", snapshot, payload)
        _write_run_state_locked(work_dir, work, len(proposals), reviewed=len(payload))
        return len(records)


def load_run_info(work_dir: Path) -> RunInfo:
    """Load one run and derive progress from validated work files."""
    work = load_work(work_dir)
    proposals = _load_proposals(work_dir, expected_snapshot=work.manifest.snapshot)
    proposal_map = {item.repo: item for item in proposals}
    reviews = _load_reviews(
        work_dir,
        expected_snapshot=work.manifest.snapshot,
        proposals=proposal_map,
    )
    metadata = _load_run_metadata(work_dir, work)
    if metadata.state != "superseded":
        metadata = metadata.model_copy(
            update={
                "state": _run_state(
                    len(work.manifest.repos), len(proposals), len(reviews)
                )
            }
        )
    return RunInfo(
        path=work_dir,
        metadata=metadata,
        proposals=len(proposals),
        reviewed=len(reviews),
        total=len(work.manifest.repos),
    )


def compare_source(
    work_dir: Path, stars: list[Star], lists: list[List]
) -> SourceChanges:
    """Compare a saved run with the current local snapshot."""
    old = load_work(work_dir)
    current = build_work(stars, lists)
    old_records = {item.repo: item for item in old.classifier_input}
    new_records = {item.repo: item for item in current.classifier_input}
    old_repos = set(old_records)
    new_repos = set(new_records)
    common = old_repos & new_repos
    return SourceChanges(
        added=sorted(new_repos - old_repos),
        removed=sorted(old_repos - new_repos),
        classifier_changed=sorted(
            repo
            for repo in common
            if old_records[repo].model_dump() != new_records[repo].model_dump()
        ),
        mapping_changed=sorted(
            repo
            for repo in common
            if old.manifest.current[repo].model_dump()
            != current.manifest.current[repo].model_dump()
        ),
    )


def refresh_work(
    source_dir: Path,
    target_dir: Path,
    stars: list[Star],
    lists: list[List],
    *,
    classifier: str,
) -> RefreshResult:
    """Create a fresh snapshot and carry forward only valid work."""
    old = load_work(source_dir)
    current = build_work(stars, lists)
    changes = compare_source(source_dir, stars, lists)
    old_records = {item.repo: item for item in old.classifier_input}
    new_records = {item.repo: item for item in current.classifier_input}
    old_proposals = {
        item.repo: item
        for item in _load_proposals(source_dir, expected_snapshot=old.manifest.snapshot)
    }
    reusable = {
        repo: proposal
        for repo, proposal in old_proposals.items()
        if repo in new_records
        and repo in old_records
        and old_records[repo].model_dump() == new_records[repo].model_dump()
    }
    old_reviews = _load_reviews(
        source_dir,
        expected_snapshot=old.manifest.snapshot,
        proposals=old_proposals,
    )
    reusable_reviews = [item for item in old_reviews if item.repo in reusable]

    extract_work(
        stars,
        lists,
        target_dir,
        classifier=classifier,
        parent_run=str(source_dir),
    )
    if reusable:
        write_proposals(
            target_dir,
            current.manifest.snapshot,
            [reusable[repo] for repo in current.manifest.repos if repo in reusable],
        )
    if reusable_reviews:
        write_reviews(target_dir, current.manifest.snapshot, reusable_reviews)
    supersede_run(source_dir, target_dir)
    return RefreshResult(
        manifest=current.manifest,
        reused_proposals=len(reusable),
        reused_reviews=len(reusable_reviews),
        changes=changes,
    )


def claim_run(work_dir: Path, classifier: str) -> RunInfo:
    """Persist legacy metadata and bind an unspecified classifier."""
    with FileLock(str(work_dir / ".lock")).acquire(timeout=5.0):
        info = load_run_info(work_dir)
        metadata = info.metadata
        if metadata.classifier not in ("unspecified", classifier):
            raise ClassificationError(
                "classifier identity differs from the saved run; use --new"
            )
        metadata = metadata.model_copy(
            update={
                "classifier": classifier,
                "state": info.metadata.state,
                "updated_at": datetime.now(UTC),
            }
        )
        _write_json(work_dir / "run.json", metadata.model_dump(mode="json"))
    return info.model_copy(update={"metadata": metadata})


def supersede_run(work_dir: Path, replacement: Path) -> None:
    """Mark one run as inactive without deleting its audit files."""
    with FileLock(str(work_dir / ".lock")).acquire(timeout=5.0):
        work = load_work(work_dir)
        metadata = _load_run_metadata(work_dir, work)
        metadata = metadata.model_copy(
            update={
                "state": "superseded",
                "superseded_by": str(replacement),
                "updated_at": datetime.now(UTC),
            }
        )
        _write_json(work_dir / "run.json", metadata.model_dump(mode="json"))


def _run_state(total: int, proposals: int, reviewed: int) -> RunState:
    if reviewed == total:
        return "complete"
    if proposals == total:
        return "reviewing"
    return "classifying"


def _load_run_metadata(work_dir: Path, work: StoredWork) -> RunMetadata:
    path = work_dir / "run.json"
    if path.exists():
        try:
            metadata = RunMetadata.model_validate(_read_json(path))
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise ClassificationError(f"invalid run metadata: {exc}") from exc
        if metadata.snapshot != work.manifest.snapshot:
            raise ClassificationError("run metadata snapshot does not match manifest")
        return metadata
    created_at = datetime.fromtimestamp(
        (work_dir / "manifest.json").stat().st_mtime, tz=UTC
    )
    return RunMetadata(
        created_at=created_at,
        updated_at=created_at,
        state="classifying",
        snapshot=work.manifest.snapshot,
    )


def _write_run_state_locked(
    work_dir: Path,
    work: StoredWork,
    proposals: int,
    *,
    reviewed: int | None = None,
) -> None:
    metadata = _load_run_metadata(work_dir, work)
    if metadata.state == "superseded":
        raise ClassificationError("cannot modify a superseded classification run")
    if reviewed is None:
        proposal_map = {
            item.repo: item
            for item in _load_proposals(
                work_dir, expected_snapshot=work.manifest.snapshot
            )
        }
        reviewed = len(
            _load_reviews(
                work_dir,
                expected_snapshot=work.manifest.snapshot,
                proposals=proposal_map,
            )
        )
    metadata = metadata.model_copy(
        update={
            "state": _run_state(len(work.manifest.repos), proposals, reviewed),
            "updated_at": datetime.now(UTC),
        }
    )
    _write_json(work_dir / "run.json", metadata.model_dump(mode="json"))


def _validate_review(
    record: ReviewRecord, proposals: dict[str, ProposalRecord]
) -> None:
    proposal = proposals.get(record.repo)
    if proposal is None:
        raise ClassificationError(
            f"review has no accepted proposal for {record.repo!r}"
        )
    if record.status == "skipped":
        if record.choice is not None or record.intent is not None:
            raise ClassificationError(
                "a skipped review must not contain a choice or Intent"
            )
        return
    if record.choice is None or record.intent is None:
        raise ClassificationError(
            "a selected review requires a Category choice and confirmed Intent"
        )


def _load_reviews(
    work_dir: Path,
    *,
    expected_snapshot: str,
    proposals: dict[str, ProposalRecord],
) -> list[ReviewRecord]:
    path = work_dir / "reviews.jsonl"
    if not path.exists():
        return []
    try:
        result: list[ReviewRecord] = []
        seen: set[str] = set()
        for item in _read_jsonl(path):
            if item.get("snapshot") != expected_snapshot:
                raise ClassificationError("review snapshot does not match manifest")
            payload = item.get("review")
            if not isinstance(payload, dict):
                raise ClassificationError("review entry must contain a review object")
            review = ReviewRecord.model_validate(payload)
            if review.repo in seen:
                raise ClassificationError(f"duplicate review for {review.repo!r}")
            _validate_review(review, proposals)
            seen.add(review.repo)
            result.append(review)
        return result
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise ClassificationError(f"invalid reviews file: {exc}") from exc


def _write_review_jsonl(
    path: Path, snapshot: str, records: Sequence[ReviewRecord]
) -> None:
    lines = [
        json.dumps(
            {"snapshot": snapshot, "review": record.model_dump(mode="json")},
            separators=(",", ":"),
        )
        for record in records
    ]
    atomic_write(path, "\n".join(lines) + ("\n" if lines else ""))


def render_markdown(
    work_dir: Path,
    output: Path,
    threshold: int,
    *,
    offset: int = 0,
    limit: int | None = None,
    pending_only: bool = False,
) -> dict[str, int | None]:
    """Join validated proposals with current mappings and write one review page."""
    if not 0 <= threshold <= 100:
        raise ClassificationError("threshold must be between 0 and 100")
    if offset < 0:
        raise ClassificationError("offset must not be negative")
    if limit is not None and limit <= 0:
        raise ClassificationError("limit must be greater than zero")
    protected = {
        (work_dir / name).resolve()
        for name in (
            "manifest.json",
            "classifier-input.jsonl",
            "proposals.jsonl",
            "reviews.jsonl",
            "run.json",
        )
    }
    if output.resolve() in protected:
        raise ClassificationError("report output must not overwrite a work file")
    with FileLock(str(work_dir / ".lock")).acquire(timeout=5.0):
        return _render_markdown_locked(
            work_dir, output, threshold, offset, limit, pending_only
        )


def _render_markdown_locked(
    work_dir: Path,
    output: Path,
    threshold: int,
    offset: int,
    limit: int | None,
    pending_only: bool,
) -> dict[str, int | None]:
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
    source_by_repo = {item.repo: item for item in work.classifier_input}
    reviews = _load_reviews(
        work_dir,
        expected_snapshot=work.manifest.snapshot,
        proposals=by_repo,
    )
    reviewed_repos = {item.repo for item in reviews}
    row_indices = [
        index
        for index, repo in enumerate(work.manifest.repos)
        if not pending_only or repo not in reviewed_repos
    ]
    blocks: list[str] = []
    unclassified = 0
    total = len(row_indices)
    end = total if limit is None else min(offset + limit, total)
    for index in row_indices[offset:end]:
        repo = work.manifest.repos[index]
        record = by_repo[repo]
        source = source_by_repo[repo]
        mapping = work.manifest.current[record.repo]
        description = source.description or "—"
        language = source.language or "—"
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
        blocks.extend(
            [
                f"## {index + 1}. {_md(record.repo)}",
                f"- **Description:** {_md(description)}",
                f"- **Language:** {_md(language)}",
                f"- **Current Lists:** {_md(current)}",
                f"- **Target Classifications:** {_md(target)}",
                "",
            ]
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(output, "\n".join(blocks) + "\n")
    summary: dict[str, int | None] = {
        "items": end - offset,
        "unclassified": unclassified,
    }
    if offset or limit is not None or pending_only:
        summary.update(
            {
                "total": total,
                "offset": offset,
                "limit": limit,
                "next_offset": end if end < total else None,
                "remaining": total - end,
            }
        )
    if pending_only:
        summary["pending"] = len(work.manifest.repos) - len(reviewed_repos)
    return summary


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
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClassificationError(f"cannot read {path}: {exc}") from exc


def _read_jsonl(path: Path) -> list[JsonObject]:
    try:
        values = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
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
