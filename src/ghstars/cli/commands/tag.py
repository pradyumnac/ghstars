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
    CODE_STATE_LOCK_HELD,
    CODE_TAG_PUSH_FAILED,
    EXIT_PARTIAL,
    EXIT_RETRYABLE,
    EXIT_TERMINAL,
    RETRYABLE_CODES,
    fail,
)
from ghstars.core import (
    StarArchivedError,
    StarListMembershipDriftError,
    StarNotFoundError,
    TagPushError,
    bulk_tag_stars,
    tag_star,
)
from ghstars.github import GitHubApiError

_REPO_OPTION = typer.Option(
    None,
    "--repo",
    help="Additional repo to tag into the same List. Repeatable (ticket 30 "
    "Scope 4 bulk tag).",
)


@app.command("tag")
def tag_cmd(
    repo: str = typer.Argument(
        ..., help="Full name of the starred repo to tag, e.g. owner/repo."
    ),
    list_name: str = typer.Argument(
        ..., help="Name of the List to add it to, e.g. 'Explore: Tool'."
    ),
    extra_repos: list[str] | None = _REPO_OPTION,
    private: bool = typer.Option(
        False,
        "--private",
        help="Create the List private if it doesn't exist yet (default: public).",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Add one or more repos to a List and push it to GitHub immediately
    (ticket 16; bulk added ticket 30 Scope 4).

    A new List is created for real immediately (spec story 48); the
    Star<->List membership itself is pushed in the same call, right
    after checking that local state agrees with GitHub's current
    membership for this repo (see `tag_star`'s docstring).

    A single target (no `--repo`) keeps its exact prior behavior: any
    failure hard-fails the whole call via `fail()`, with the specific
    machine code for what went wrong. More than one target isolates each
    repo's failure from the others (`bulk_tag_stars()`) and reports one
    result per target instead.
    """
    client = cli.get_client()
    store = cli.get_store()

    if extra_repos:
        full_names = [repo, *extra_repos]
        outcomes = bulk_tag_stars(
            client, store, full_names, list_name, is_private=private
        )
        successes = sum(1 for outcome in outcomes if outcome.error is None)

        if json_output:
            typer.echo(
                json.dumps(
                    {
                        "targets": full_names,
                        "results": [
                            {
                                "full_name": outcome.full_name,
                                "tagged": outcome.error is None,
                                "list_ids": (
                                    outcome.result.star.list_ids
                                    if outcome.result is not None
                                    else None
                                ),
                                "removed_list_ids": (
                                    outcome.result.removed_list_ids
                                    if outcome.result is not None
                                    else None
                                ),
                                "error": outcome.error,
                                "error_code": outcome.error_code,
                            }
                            for outcome in outcomes
                        ],
                    }
                )
            )
        else:
            for outcome in outcomes:
                if outcome.error is None:
                    typer.echo(f"Tagged {outcome.full_name} into {list_name!r}.")
                else:
                    typer.echo(f"Failed to tag {outcome.full_name}: {outcome.error}")

        if successes == len(outcomes):
            return
        if successes == 0 and all(
            outcome.error_code in RETRYABLE_CODES for outcome in outcomes
        ):
            raise typer.Exit(code=EXIT_RETRYABLE)
        raise typer.Exit(code=EXIT_TERMINAL if successes == 0 else EXIT_PARTIAL)

    try:
        result = tag_star(client, store, repo, list_name, is_private=private)
    except StarNotFoundError:
        fail(
            f"no local record for {repo!r}. Run `ghstars sync` first.",
            code=CODE_NO_LOCAL_RECORD,
            json_output=json_output,
            target=repo,
        )
    except StarArchivedError:
        fail(
            f"{repo!r} is Archived (unstarred) locally — nothing to tag.",
            code=CODE_STAR_ARCHIVED,
            json_output=json_output,
            target=repo,
        )
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
        # Report lock contention without a traceback; no state was written.
        fail(
            "could not acquire the local state lock — another ghstars "
            "command may be running. Try again.",
            code=CODE_STATE_LOCK_HELD,
            json_output=json_output,
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
