import json

import typer

from ghstars import cli
from ghstars.cli import app  # imported by name for mypy; see commands/sync.py


@app.command("ratelimit")
def ratelimit_cmd(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Report the live GitHub API rate limit (ticket 30 Scope 5).

    A separate, explicit network call -- never folded into `status`,
    which stays offline. Does not run a sync; it is the one-shot
    `GitHubClient.check_rate_limit()` call `sync` itself makes before
    fetching anything.
    """
    status = cli.get_client().check_rate_limit()

    if json_output:
        typer.echo(json.dumps(status.model_dump(mode="json")))
        return

    typer.echo(f"Remaining: {status.remaining}/{status.limit}")
    typer.echo(f"Ok: {status.ok}")
