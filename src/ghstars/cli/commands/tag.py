import json

import typer
from filelock import Timeout

from ghstars import cli
from ghstars.cli import app  # imported by name for mypy; see commands/sync.py
from ghstars.cli.errors import fail
from ghstars.core import (
    StarArchivedError,
    StarListMembershipDriftError,
    StarNotFoundError,
    TagPushError,
    tag_star,
)
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
    """Add a repo to a List and push it to GitHub immediately (ticket 16).

    A new List is created for real immediately (spec story 48); the
    Star<->List membership itself is pushed in the same call, right
    after checking that local state agrees with GitHub's current
    membership for this repo (see `tag_star`'s docstring).
    """
    client = cli.get_client()
    store = cli.get_store()
    try:
        result = tag_star(client, store, repo, list_name, is_private=private)
    except StarNotFoundError:
        fail(f"no local record for {repo!r}. Run `ghstars sync` first.")
    except StarArchivedError:
        fail(f"{repo!r} is Archived (unstarred) locally — nothing to tag.")
    except StarListMembershipDriftError as exc:
        fail(str(exc))
    except TagPushError as exc:
        fail(str(exc))
    except GitHubApiError as exc:
        fail(str(exc))
    except Timeout:
        # `tag_star()` holds the state lock across its GitHub push now
        # (ticket 16), longer than before -- a concurrent `ghstars`
        # command waiting on the same lock can time out here instead of
        # the usual quick acquire. A clean error beats a raw traceback;
        # the repo was not modified either way (the lock never acquired).
        fail(
            "could not acquire the local state lock — another ghstars "
            "command may be running. Try again."
        )

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "full_name": repo,
                    "list_ids": result.star.list_ids,
                    "removed_list_ids": result.removed_list_ids,
                }
            )
        )
        return
    message = f"Tagged {repo} into {list_name!r}."
    if result.removed_list_ids:
        message += f" (removed from {len(result.removed_list_ids)} other List(s))"
    typer.echo(message)
