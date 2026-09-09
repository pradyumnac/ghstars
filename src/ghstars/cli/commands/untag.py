import json

import typer
from filelock import Timeout

from ghstars import cli
from ghstars.cli import app  # imported by name for mypy; see commands/sync.py
from ghstars.cli.errors import (
    CODE_LIST_MEMBERSHIP_DRIFT,
    CODE_NETWORK_FAILURE,
    CODE_NO_LOCAL_RECORD,
    CODE_STAR_ARCHIVED,
    CODE_STAR_NOT_IN_LIST,
    CODE_STATE_LOCK_HELD,
    CODE_TAG_PUSH_FAILED,
    fail,
)
from ghstars.core import (
    StarArchivedError,
    StarListMembershipDriftError,
    StarNotFoundError,
    StarNotInListError,
    TagPushError,
    untag_star,
)
from ghstars.github import GitHubApiError


@app.command("untag")
def untag_cmd(
    repo: str = typer.Argument(
        ..., help="Full name of the starred repo to untag, e.g. owner/repo."
    ),
    list_name: str = typer.Argument(
        ..., help="Name of the List to remove it from, e.g. 'Explore: General'."
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Remove one repo from one List, and push it to GitHub immediately.

    Every other List the repo belongs to is left untouched. `tag`'s
    same-Category strip removes a sibling only as a side effect of
    adding a new one; `unstar` removes every membership at once. This
    is the one case neither covers: dropping a single, specific
    membership on its own -- for example, taking a Star out of the
    triage inbox (`*: General`) once it has a real Category elsewhere.
    """
    client = cli.get_client()
    store = cli.get_store()

    try:
        result = untag_star(client, store, repo, list_name)
    except StarNotFoundError:
        fail(
            f"no local record for {repo!r}. Run `ghstars sync` first.",
            code=CODE_NO_LOCAL_RECORD,
            json_output=json_output,
            target=repo,
        )
    except StarArchivedError:
        fail(
            f"{repo!r} is Archived (unstarred) locally — nothing to untag.",
            code=CODE_STAR_ARCHIVED,
            json_output=json_output,
            target=repo,
        )
    except StarNotInListError as exc:
        fail(str(exc), code=CODE_STAR_NOT_IN_LIST, json_output=json_output, target=repo)
    except StarListMembershipDriftError as exc:
        fail(
            str(exc),
            code=CODE_LIST_MEMBERSHIP_DRIFT,
            json_output=json_output,
            target=repo,
        )
    except TagPushError as exc:
        fail(str(exc), code=CODE_TAG_PUSH_FAILED, json_output=json_output, target=repo)
    except GitHubApiError as exc:
        fail(str(exc), code=CODE_NETWORK_FAILURE, json_output=json_output, target=repo)
    except Timeout:
        fail(
            "could not acquire the local state lock — another ghstars "
            "command may be running. Try again.",
            code=CODE_STATE_LOCK_HELD,
            json_output=json_output,
        )

    if json_output:
        typer.echo(json.dumps({"full_name": repo, "list_ids": result.star.list_ids}))
        return
    typer.echo(f"Untagged {repo} from {list_name!r}.")
