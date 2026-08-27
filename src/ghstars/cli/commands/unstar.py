import json

import typer
from filelock import Timeout

from ghstars import cli
from ghstars.cli import app  # imported by name for mypy; see commands/sync.py
from ghstars.cli.errors import CODE_NETWORK_FAILURE, CODE_STATE_LOCK_HELD, fail
from ghstars.core import unstar_star
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
        result = unstar_star(client, store, repo)
    except GitHubApiError as exc:
        fail(str(exc), code=CODE_NETWORK_FAILURE, json_output=json_output, target=repo)
    except Timeout:
        # Report remote success separately from local lock failure.
        fail(
            f"unstarred {repo} on GitHub, but could not acquire the local "
            "state lock to archive it locally — another ghstars command "
            "may be running. Run `ghstars sync` once it finishes to pick "
            "up the change.",
            code=CODE_STATE_LOCK_HELD,
            json_output=json_output,
            target=repo,
        )

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "full_name": result.full_name,
                    "unstarred": True,
                    "archived_locally": result.found_locally,
                }
            )
        )
        return
    if result.found_locally:
        typer.echo(f"Unstarred {repo}.")
    else:
        typer.echo(
            f"Unstarred {repo} on GitHub (no local record to archive — "
            "run `ghstars sync` to pick it up)."
        )
