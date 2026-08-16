import json

import typer

from ghstars.cli.deps import get_client, get_store
from ghstars.cli.errors import fail
from ghstars.core import RateLimitExceededError, sync
from ghstars.core.models import Star
from ghstars.github import GitHubApiError

app = typer.Typer(no_args_is_help=True)

STAR_FIELDS = set(Star.model_fields.keys())
DEFAULT_LIST_FIELDS = ["full_name", "language", "stargazer_count"]


@app.command("sync")
def sync_cmd(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Fetch stars from GitHub into local state."""
    client = get_client()
    store = get_store()
    try:
        result = sync(client, store)
    except (RateLimitExceededError, GitHubApiError) as exc:
        fail(str(exc))

    if json_output:
        typer.echo(json.dumps(result.model_dump(mode="json")))
        return
    typer.echo(f"Synced {result.star_count} star(s).")


@app.command("list")
def list_cmd(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    fields: str | None = typer.Option(
        None, "--fields", help="Comma-separated field names to include."
    ),
) -> None:
    """List locally synced stars."""
    store = get_store()
    stars = store.load_stars()

    selected: list[str] | None = None
    if fields is not None:
        selected = [f.strip() for f in fields.split(",") if f.strip()]
        unknown = [f for f in selected if f not in STAR_FIELDS]
        if unknown:
            fail(f"unknown field(s): {', '.join(unknown)}")

    if json_output:
        rows = [
            star.model_dump(mode="json", include=set(selected) if selected else None)
            for star in stars
        ]
        typer.echo(json.dumps(rows))
        return

    if not stars:
        typer.echo("No stars synced yet. Run `ghstars sync` first.")
        return

    display_fields = selected or DEFAULT_LIST_FIELDS
    for star in stars:
        typer.echo(" ".join(str(getattr(star, f)) for f in display_fields))
