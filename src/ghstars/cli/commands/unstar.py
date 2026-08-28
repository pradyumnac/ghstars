import json

import typer
from filelock import Timeout

from ghstars import cli
from ghstars.cli import app  # imported by name for mypy; see commands/sync.py
from ghstars.cli.errors import (
    CODE_INVALID_INPUT,
    CODE_NETWORK_FAILURE,
    CODE_STATE_LOCK_HELD,
    EXIT_PARTIAL,
    EXIT_TERMINAL,
    fail,
)
from ghstars.core import bulk_unstar_stars, unstar_star
from ghstars.github import GitHubApiError

_REPO_OPTION = typer.Option(
    None,
    "--repo",
    help="Additional repo to unstar in the same call. Repeatable (ticket 30 "
    "Scope 4 bulk unstar).",
)


@app.command("unstar")
def unstar_cmd(
    repo: str = typer.Argument(
        ..., help="Full name of the starred repo to unstar, e.g. owner/repo."
    ),
    extra_repos: list[str] | None = _REPO_OPTION,
    yes: bool = typer.Option(
        False, "--yes", help="Confirm the unstar. Required, single or bulk."
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Unstar one or more repos on GitHub for real, then mark their local
    records Archived.

    A real, visible mutation on the user's GitHub account (spec story 8).
    The local record is never deleted; it is kept and marked Archived
    (spec story 6), distinct from a List's Retired Intent (CONTEXT.md).

    Every unstar, single or bulk, requires `--yes` (ticket 30 Decision 1).
    There is no interactive prompt -- a confirmation gated on a terminal
    would not work for a non-interactive (agent) caller, so `--yes` is the
    whole confirmation contract, not a fallback for one. Without it, the
    command fails before mutating anything and lists every target it would
    have unstarred. Only an explicit repository name can select a target
    -- no Filter, search term, standard input stream, or wildcard.
    """
    full_names = [repo, *(extra_repos or [])]

    if not yes:
        fail(
            "unstar requires --yes to confirm. Targets: "
            + ", ".join(full_names)
            + ".",
            code=CODE_INVALID_INPUT,
            json_output=json_output,
        )

    if len(full_names) > 1:
        typer.echo(f"Targets: {', '.join(full_names)}", err=json_output)

    client = cli.get_client()
    store = cli.get_store()

    if len(full_names) == 1:
        try:
            result = unstar_star(client, store, repo)
        except GitHubApiError as exc:
            fail(
                str(exc), code=CODE_NETWORK_FAILURE, json_output=json_output, target=repo
            )
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
        return

    outcomes = bulk_unstar_stars(client, store, full_names)
    successes = sum(1 for outcome in outcomes if outcome.error is None)

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "targets": full_names,
                    "results": [
                        {
                            "full_name": outcome.full_name,
                            "unstarred": outcome.error is None,
                            "archived_locally": (
                                outcome.result.found_locally
                                if outcome.result is not None
                                else None
                            ),
                            "error": outcome.error,
                        }
                        for outcome in outcomes
                    ],
                }
            )
        )
    else:
        for outcome in outcomes:
            if outcome.error is None:
                typer.echo(f"Unstarred {outcome.full_name}.")
            else:
                typer.echo(f"Failed to unstar {outcome.full_name}: {outcome.error}")

    if successes == len(outcomes):
        return
    raise typer.Exit(code=EXIT_TERMINAL if successes == 0 else EXIT_PARTIAL)
