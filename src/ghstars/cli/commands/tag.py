import json

import typer

from ghstars import cli
from ghstars.cli import app  # imported by name for mypy; see commands/sync.py
from ghstars.cli.errors import fail
from ghstars.core import StarArchivedError, StarNotFoundError, tag_star
from ghstars.github import GitHubApiError


@app.command("tag")
def tag_cmd(
    repo: str = typer.Argument(
        ..., help="Full name of the starred repo to tag, e.g. owner/repo."
    ),
    list_name: str = typer.Argument(
        ..., help="Name of the List to add it to, e.g. 'Explore: Tool'."
    ),
    private: bool = typer.Option(
        False,
        "--private",
        help="Create the List private if it doesn't exist yet (default: public).",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Stage a repo for addition to a List. Run `ghstars sync` to push it.

    A new List is created for real immediately (spec story 48); the
    Star<->List membership itself is staged locally and pushed at the
    next sync, so a concurrent GitHub-side change has something to be
    checked against (ticket 05).
    """
    client = cli.get_client()
    store = cli.get_store()
    try:
        result = tag_star(client, store, repo, list_name, is_private=private)
    except StarNotFoundError:
        fail(f"no local record for {repo!r}. Run `ghstars sync` first.")
    except StarArchivedError:
        fail(f"{repo!r} is Archived (unstarred) locally — nothing to tag.")
    except GitHubApiError as exc:
        fail(str(exc))

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "full_name": repo,
                    "pending_list_ids": result.star.pending_list_ids,
                    "removed_list_ids": result.removed_list_ids,
                }
            )
        )
        return
    message = f"Staged {repo} for {list_name!r}. Run `ghstars sync` to push it."
    if result.removed_list_ids:
        message += f" (removed from {len(result.removed_list_ids)} other List(s))"
    typer.echo(message)
