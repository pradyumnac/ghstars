import json

import typer
from pydantic import BaseModel

from ghstars.cli.deps import get_client, get_store
from ghstars.cli.errors import fail
from ghstars.core import RateLimitExceededError, sync
from ghstars.core.models import List, Star
from ghstars.github import GitHubApiError

app = typer.Typer(no_args_is_help=True)

STAR_FIELDS = set(Star.model_fields.keys())
DEFAULT_STAR_FIELDS = ["full_name", "language", "stargazer_count"]

LIST_FIELDS = set(List.model_fields.keys())
DEFAULT_LISTS_FIELDS = ["name", "intent", "category", "is_private", "malformed"]


@app.command("sync")
def sync_cmd(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Fetch stars and Lists from GitHub into local state."""
    client = get_client()
    store = get_store()
    try:
        result = sync(client, store)
    except (RateLimitExceededError, GitHubApiError) as exc:
        fail(str(exc))

    if json_output:
        typer.echo(json.dumps(result.model_dump(mode="json")))
        return
    typer.echo(f"Synced {result.star_count} star(s), {result.list_count} list(s).")


def _render_records[ModelT: BaseModel](
    records: list[ModelT],
    *,
    field_names: set[str],
    default_fields: list[str],
    empty_message: str,
    json_output: bool,
    fields: str | None,
) -> None:
    """Shared `--json`/`--fields` rendering for list-returning commands.

    Every list-returning command follows the same contract (spec stories
    28-30): `--json` for structured output, `--fields` to select a subset
    (validated against `field_names`, unknown fields hard-fail via `fail()`
    rather than being silently ignored), plain-text otherwise.
    """
    selected: list[str] | None = None
    if fields is not None:
        selected = [f.strip() for f in fields.split(",") if f.strip()]
        unknown = [f for f in selected if f not in field_names]
        if unknown:
            fail(f"unknown field(s): {', '.join(unknown)}")

    if json_output:
        rows = [
            record.model_dump(mode="json", include=set(selected) if selected else None)
            for record in records
        ]
        typer.echo(json.dumps(rows))
        return

    if not records:
        typer.echo(empty_message)
        return

    display_fields = selected or default_fields
    for record in records:
        typer.echo(" ".join(str(getattr(record, f)) for f in display_fields))


@app.command("list")
def list_cmd(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    fields: str | None = typer.Option(
        None, "--fields", help="Comma-separated field names to include."
    ),
) -> None:
    """List locally synced stars."""
    stars = get_store().load_stars()
    _render_records(
        stars,
        field_names=STAR_FIELDS,
        default_fields=DEFAULT_STAR_FIELDS,
        empty_message="No stars synced yet. Run `ghstars sync` first.",
        json_output=json_output,
        fields=fields,
    )


@app.command("lists")
def lists_cmd(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    fields: str | None = typer.Option(
        None, "--fields", help="Comma-separated field names to include."
    ),
) -> None:
    """List locally synced GitHub Lists, with parsed Intent/Category."""
    lists = get_store().load_lists()
    _render_records(
        lists,
        field_names=LIST_FIELDS,
        default_fields=DEFAULT_LISTS_FIELDS,
        empty_message="No Lists synced yet. Run `ghstars sync` first.",
        json_output=json_output,
        fields=fields,
    )
