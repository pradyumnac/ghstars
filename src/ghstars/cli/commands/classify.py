"""Offline classification-debt work-directory commands."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

import typer
from filelock import Timeout
from pydantic import ValidationError

from ghstars import cli
from ghstars.cli import classify_app
from ghstars.cli.deps import get_ghstars_home
from ghstars.cli.errors import CODE_INVALID_INPUT, CODE_STATE_LOCK_HELD, fail
from ghstars.core.classification import (  # pyright: ignore[reportMissingImports]
    ClassificationError,
    ProposalRecord,
    ReviewRecord,
    build_work,
    claim_run,
    compare_source,
    extract_work,
    load_run_info,
    load_work,
    refresh_work,
    render_markdown,
    supersede_run,
    write_proposals,
    write_reviews,
)

_WORK_DIR_OPTION = typer.Option(
    None,
    "--work-dir",
    help="Classification work directory. Defaults to ghstars data.",
)
_OUTPUT_OPTION = typer.Option(..., "--output", help="Markdown output path.")
_SNAPSHOT_OPTION = typer.Option(..., "--snapshot", help="Manifest snapshot ID.")
_INPUT_OPTION = typer.Option(..., "--input", help="Classifier JSONL file.")
_RESUME_OPTION = typer.Option(None, "--resume", help="Run directory to resume.")
_CLASSIFIER_OPTION = typer.Option(
    "unspecified", "--classifier", help="Stable classifier model identifier."
)
_CLASSIFICATION_INPUT_ERRORS = (
    OSError,
    UnicodeDecodeError,
    json.JSONDecodeError,
    ValidationError,
    ClassificationError,
)


def _classification_fail(message: str, json_output: bool) -> NoReturn:
    fail(message, code=CODE_INVALID_INPUT, json_output=json_output)


def _work_lock_fail(json_output: bool) -> NoReturn:
    fail(
        "could not acquire the classification work lock. Try again.",
        code=CODE_STATE_LOCK_HELD,
        json_output=json_output,
    )


def _read_jsonl_objects(path: Path, label: str) -> list[dict[str, object]]:
    try:
        values: list[object] = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClassificationError(f"cannot read {label} input: {exc}") from exc
    if not all(isinstance(item, dict) for item in values):
        raise ClassificationError(f"{label} input must contain JSON objects")
    return [item for item in values if isinstance(item, dict)]


def _classification_root() -> Path:
    return get_ghstars_home() / "data" / "classify"


def _new_work_dir(root: Path | None = None) -> Path:
    root = root or _classification_root()
    root.mkdir(parents=True, exist_ok=True)
    stem = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    work_dir = root / stem
    suffix = 1
    while work_dir.exists():
        work_dir = root / f"{stem}-{suffix}"
        suffix += 1
    return Path(work_dir)


def _managed_runs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.iterdir()
        if path.is_dir() and (path / "manifest.json").exists()
    )


def _best_active_run(
    paths: list[Path],
    snapshot: str,
    *,
    unclassified_only: bool,
    limit: int | None,
) -> Path | None:
    infos = [load_run_info(path) for path in paths]
    active = [info for info in infos if info.metadata.state != "superseded"]
    same_scope = []
    for info in active:
        manifest = load_work(info.path).manifest
        if manifest.unclassified_only == unclassified_only and manifest.limit == limit:
            same_scope.append(info)
    if not same_scope:
        return None
    matching = [info for info in same_scope if info.metadata.snapshot == snapshot]
    candidates = matching or same_scope
    return max(
        candidates,
        key=lambda info: (
            info.reviewed,
            info.proposals,
            info.metadata.updated_at,
            info.metadata.created_at,
        ),
    ).path


@classify_app.command("extract")
def extract_cmd(
    work_dir: Path | None = _WORK_DIR_OPTION,
    resume: Path | None = _RESUME_OPTION,
    new: bool = typer.Option(False, "--new", help="Start without reused work."),
    classifier: str = _CLASSIFIER_OPTION,
    unclassified_only: bool = typer.Option(
        False,
        "--unclassified-only",
        help="Include only Stars with no Category or only General.",
    ),
    limit: int | None = typer.Option(
        None,
        "--limit",
        min=1,
        help="Maximum Stars after the scope filter.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Create, resume, or refresh an offline classification run."""
    if resume is not None and work_dir is not None:
        _classification_fail("use either --resume or --work-dir, not both", json_output)
    if new and resume is not None:
        _classification_fail("--new cannot be used with --resume", json_output)
    try:
        store = cli.get_read_only_store()
        stars, lists = store.read_existing_stars_and_lists()
        current = build_work(
            stars,
            lists,
            unclassified_only=unclassified_only,
            limit=limit,
        )
        root = _classification_root()
        # An explicit work directory is an isolated component run. It must not
        # inspect or supersede managed runs under the user's ghstars home.
        runs = _managed_runs(root) if work_dir is None else []
        selected = resume
        if (
            selected is None
            and work_dir is not None
            and (work_dir / "manifest.json").exists()
        ):
            selected = work_dir
        if selected is None and not new and work_dir is None:
            selected = _best_active_run(
                runs,
                current.manifest.snapshot,
                unclassified_only=unclassified_only,
                limit=limit,
            )
        if selected is None and work_dir is not None and not new:
            active = [
                path
                for path in runs
                if load_run_info(path).metadata.state != "superseded"
            ]
            if active:
                raise ClassificationError(
                    "an active classification run exists; omit --work-dir to "
                    "resume it, or use --new"
                )

        action = "new"
        reused_proposals = 0
        reused_reviews = 0
        changes: dict[str, list[str]] | None = None
        if selected is not None and not new:
            info = load_run_info(selected)
            if (
                info.metadata.snapshot == current.manifest.snapshot
                and info.metadata.state != "superseded"
            ):
                info = claim_run(selected, classifier)
                work_dir = selected
                manifest = current.manifest
                action = "resume"
            elif info.metadata.classifier not in ("unspecified", classifier):
                raise ClassificationError(
                    "classifier identity differs from the saved run; use --new"
                )
            else:
                target = _new_work_dir(root)
                refreshed = refresh_work(
                    selected,
                    target,
                    stars,
                    lists,
                    classifier=classifier,
                )
                work_dir = target
                manifest = refreshed.manifest
                reused_proposals = refreshed.reused_proposals
                reused_reviews = refreshed.reused_reviews
                changes = refreshed.changes.model_dump(mode="json")
                action = "refresh"
        else:
            target = work_dir or _new_work_dir(root)
            if (target / "manifest.json").exists():
                raise ClassificationError(
                    f"classification work directory already exists: {target}"
                )
            manifest = extract_work(
                stars,
                lists,
                target,
                classifier=classifier,
                unclassified_only=unclassified_only,
                limit=limit,
            )
            work_dir = target
            for path in runs:
                info = load_run_info(path)
                if info.metadata.state != "superseded":
                    supersede_run(path, target)
    except Timeout:
        fail(
            "could not acquire the local state lock — another ghstars command "
            "may be running. Try again.",
            code=CODE_STATE_LOCK_HELD,
            json_output=json_output,
        )
    except (
        OSError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValidationError,
        ClassificationError,
    ) as exc:
        _classification_fail(str(exc), json_output)
    info = load_run_info(work_dir)
    payload = {
        "action": action,
        "work_dir": str(work_dir),
        "resume_path": str(work_dir),
        "snapshot": manifest.snapshot,
        "state": info.metadata.state,
        "count": len(manifest.repos),
        "proposals": info.proposals,
        "reviewed": info.reviewed,
        "pending_proposals": info.total - info.proposals,
        "pending_reviews": info.total - info.reviewed,
        "reused_proposals": reused_proposals,
        "reused_reviews": reused_reviews,
        "changes": changes,
        "unclassified_only": manifest.unclassified_only,
        "limit": manifest.limit,
    }
    if json_output:
        typer.echo(json.dumps(payload))
    else:
        typer.echo(f"Classification action: {action}.")
        typer.echo(f"Run: {work_dir}")
        typer.echo(f"Snapshot: {manifest.snapshot}")
        typer.echo(
            f"Progress: {info.proposals}/{info.total} proposals; "
            f"{info.reviewed}/{info.total} reviews."
        )


@classify_app.command("write")
def write_cmd(
    work_dir: Path = _WORK_DIR_OPTION,
    snapshot: str = _SNAPSHOT_OPTION,
    input_path: Path = _INPUT_OPTION,
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Validate and store one classifier proposal batch."""
    try:
        records = [
            ProposalRecord.model_validate(item)
            for item in _read_jsonl_objects(input_path, "classifier")
        ]
        count = write_proposals(work_dir, snapshot, records)
    except Timeout:
        _work_lock_fail(json_output)
    except _CLASSIFICATION_INPUT_ERRORS as exc:
        _classification_fail(str(exc), json_output)
    payload = {"accepted": count, "snapshot": snapshot}
    if json_output:
        typer.echo(json.dumps(payload))
    else:
        typer.echo(f"Accepted {count} proposals.")


@classify_app.command("review")
def review_cmd(
    work_dir: Path = _WORK_DIR_OPTION,
    snapshot: str = _SNAPSHOT_OPTION,
    input_path: Path = _INPUT_OPTION,
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Validate and store one user review batch."""
    try:
        records = [
            ReviewRecord.model_validate(item)
            for item in _read_jsonl_objects(input_path, "review")
        ]
        count = write_reviews(work_dir, snapshot, records)
        info = load_run_info(work_dir)
    except Timeout:
        _work_lock_fail(json_output)
    except _CLASSIFICATION_INPUT_ERRORS as exc:
        _classification_fail(str(exc), json_output)
    payload = {
        "accepted": count,
        "snapshot": snapshot,
        "reviewed": info.reviewed,
        "pending": info.total - info.reviewed,
        "state": info.metadata.state,
    }
    if json_output:
        typer.echo(json.dumps(payload))
    else:
        typer.echo(f"Accepted {count} review decisions.")
        typer.echo(f"Pending reviews: {info.total - info.reviewed}.")


@classify_app.command("check")
def check_cmd(
    work_dir: Path = _WORK_DIR_OPTION,
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Compare a run with the current local Stars and Lists."""
    try:
        store = cli.get_read_only_store()
        stars, lists = store.read_existing_stars_and_lists()
        changes = compare_source(work_dir, stars, lists)
        info = load_run_info(work_dir)
    except Timeout:
        fail(
            "could not acquire the local state lock. Try again.",
            code=CODE_STATE_LOCK_HELD,
            json_output=json_output,
        )
    except (
        OSError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValidationError,
        ClassificationError,
    ) as exc:
        _classification_fail(str(exc), json_output)
    payload = {
        "state": "stale" if changes.changed else "current",
        "matches": not changes.changed,
        "snapshot": info.metadata.snapshot,
        "changes": changes.model_dump(mode="json"),
    }
    if json_output:
        typer.echo(json.dumps(payload))
    elif changes.changed:
        typer.echo("Classification run is stale.")
    else:
        typer.echo("Classification run matches local state.")


@classify_app.command("render")
def render_cmd(
    work_dir: Path | None = _WORK_DIR_OPTION,
    output: Path = _OUTPUT_OPTION,
    threshold: int = typer.Option(70, "--threshold", help="Minimum Category score."),
    offset: int = typer.Option(0, "--offset", help="First numbered item to render."),
    limit: int | None = typer.Option(
        None, "--limit", help="Maximum items to render in this review batch."
    ),
    pending: bool = typer.Option(
        False, "--pending", help="Render only repositories without a review."
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Join proposals with current Lists and write one review batch."""
    if work_dir is None:
        _classification_fail("--work-dir is required for render", json_output)
    try:
        summary = render_markdown(
            work_dir,
            output,
            threshold,
            offset=offset,
            limit=limit,
            pending_only=pending,
        )
    except Timeout:
        fail(
            "could not acquire the classification work lock. Try again.",
            code=CODE_STATE_LOCK_HELD,
            json_output=json_output,
        )
    except (OSError, ClassificationError) as exc:
        _classification_fail(str(exc), json_output)
    payload = {"output": str(output), **summary}
    if json_output:
        typer.echo(json.dumps(payload))
    else:
        typer.echo(f"Wrote {summary['items']} items to {output}.")
        typer.echo(f"Unclassified below threshold: {summary['unclassified']}.")
