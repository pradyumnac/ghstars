import json
from datetime import UTC, datetime

import typer

from ghstars.cli.deps import get_client, get_store
from ghstars.cli.errors import fail
from ghstars.core import RateLimitExceededError, archive_star, sync
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


@app.command("unstar")
def unstar_cmd(
    repo: str = typer.Argument(
        ..., help="Full name of the starred repo to unstar, e.g. owner/repo."
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Unstar a repo on GitHub for real, then mark its local record Archived.

    A real, visible mutation against the authenticated user's GitHub
    account (spec story 8) — this is a control surface, not a local-only
    shadow copy. The local record (if one exists) is never deleted; it is
    kept and marked Archived (spec story 6), distinct from a List's
    Retired Intent (see CONTEXT.md).
    """
    client = get_client()
    store = get_store()
    try:
        client.remove_star(repo)
    except GitHubApiError as exc:
        fail(str(exc))

    # The GitHub-side unstar above already succeeded regardless of what
    # follows; hold the lock across this read-modify-write so a concurrent
    # `ghstars sync` can't read a stale snapshot and clobber this update
    # (spec story 33), the same reasoning as sync()'s own locked span.
    now = datetime.now(UTC)
    with store.lock():
        stars = store.load_stars()
        found_locally = any(star.full_name == repo for star in stars)
        updated = [
            archive_star(star, now=now)
            if star.full_name == repo and not star.archived
            else star
            for star in stars
        ]
        store.save_stars(updated)

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "full_name": repo,
                    "unstarred": True,
                    "archived_locally": found_locally,
                }
            )
        )
        return
    if found_locally:
        typer.echo(f"Unstarred {repo}.")
    else:
        typer.echo(
            f"Unstarred {repo} on GitHub (no local record to archive — "
            "run `ghstars sync` to pick it up)."
        )
