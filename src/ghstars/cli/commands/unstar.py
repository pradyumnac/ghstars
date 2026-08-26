import json
from datetime import UTC, datetime

import typer
from filelock import Timeout

from ghstars import cli
from ghstars.cli import app  # imported by name for mypy; see commands/sync.py
from ghstars.cli.errors import fail
from ghstars.core import archive_star, remove_star_from_lists
from ghstars.github import GitHubApiError


@app.command("unstar")
def unstar_cmd(
    repo: str = typer.Argument(
        ..., help="Full name of the starred repo to unstar, e.g. owner/repo."
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Unstar a repo on GitHub for real, then mark its local record Archived.

    A real, visible mutation on the user's GitHub account (spec story 8).
    The local record is never deleted; it is kept and marked Archived
    (spec story 6), distinct from a List's Retired Intent (CONTEXT.md).
    """
    client = cli.get_client()
    store = cli.get_store()
    try:
        client.remove_star(repo)
    except GitHubApiError as exc:
        fail(str(exc))

    # The GitHub-side unstar already succeeded. Hold the lock across this
    # read-modify-write so a concurrent `ghstars sync` cannot clobber it
    # (spec story 33), same as sync()'s locked span.
    now = datetime.now(UTC)
    try:
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
            store.save_lists(remove_star_from_lists(store.load_lists(), repo))
    except Timeout:
        # The GitHub-side unstar above already succeeded -- only the
        # local archive-and-save is blocked by a concurrent `ghstars`
        # command holding the lock. Say so explicitly: a plain "try
        # again" here would wrongly imply the unstar itself needs
        # retrying too.
        fail(
            f"unstarred {repo} on GitHub, but could not acquire the local "
            "state lock to archive it locally — another ghstars command "
            "may be running. Run `ghstars sync` once it finishes to pick "
            "up the change."
        )

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
