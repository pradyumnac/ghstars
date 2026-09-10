"""Offline classification-debt work-directory commands."""

import json
from pathlib import Path
from typing import NoReturn

import typer
from filelock import Timeout
from pydantic import ValidationError

from ghstars import cli
from ghstars.cli import classify_app
from ghstars.cli.errors import CODE_INVALID_INPUT, CODE_STATE_LOCK_HELD, fail
from ghstars.core.classification import (  # pyright: ignore[reportMissingImports]
    ClassificationError,
    ProposalRecord,
    extract_work,
    render_markdown,
    write_proposals,
)

_WORK_DIR_OPTION = typer.Option(..., "--work-dir", help="Runtime work directory.")
_OUTPUT_OPTION = typer.Option(..., "--output", help="Markdown output path.")
_SNAPSHOT_OPTION = typer.Option(..., "--snapshot", help="Manifest snapshot ID.")
_INPUT_OPTION = typer.Option(..., "--input", help="Classifier JSONL file.")


def _classification_fail(message: str, json_output: bool) -> NoReturn:
    fail(message, code=CODE_INVALID_INPUT, json_output=json_output)


@classify_app.command("extract")
def extract_cmd(
    work_dir: Path = _WORK_DIR_OPTION,
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Write the offline classifier input and hidden current mapping."""
    try:
        store = cli.get_read_only_store()
        stars, lists = store.read_existing_stars_and_lists()
        manifest = extract_work(stars, lists, work_dir)
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
    payload = {
        "work_dir": str(work_dir),
        "snapshot": manifest.snapshot,
        "count": len(manifest.repos),
    }
    if json_output:
        typer.echo(json.dumps(payload))
    else:
        typer.echo(f"Extracted {payload['count']} Stars into {work_dir}.")
        typer.echo(f"Snapshot: {manifest.snapshot}")


@classify_app.command("write")
def write_cmd(
    work_dir: Path = _WORK_DIR_OPTION,
    snapshot: str = _SNAPSHOT_OPTION,
    input_path: Path = _INPUT_OPTION,
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Validate and store one classifier proposal batch."""
    try:
        raw_records = [
            json.loads(line)
            for line in input_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if not all(isinstance(item, dict) for item in raw_records):
            raise ClassificationError("classifier input must contain JSON objects")
        records = [ProposalRecord.model_validate(item) for item in raw_records]
        count = write_proposals(work_dir, snapshot, records)
    except Timeout:
        fail(
            "could not acquire the classification work lock. Try again.",
            code=CODE_STATE_LOCK_HELD,
            json_output=json_output,
        )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValidationError,
        ClassificationError,
    ) as exc:
        _classification_fail(str(exc), json_output)
    payload = {"accepted": count, "snapshot": snapshot}
    if json_output:
        typer.echo(json.dumps(payload))
    else:
        typer.echo(f"Accepted {count} proposals.")


@classify_app.command("render")
def render_cmd(
    work_dir: Path = _WORK_DIR_OPTION,
    output: Path = _OUTPUT_OPTION,
    threshold: int = typer.Option(70, "--threshold", help="Minimum Category score."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Join proposals with current Lists and write the review table."""
    try:
        summary = render_markdown(work_dir, output, threshold)
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
        typer.echo(f"Wrote {summary['rows']} rows to {output}.")
        typer.echo(f"Unclassified below threshold: {summary['unclassified']}.")
