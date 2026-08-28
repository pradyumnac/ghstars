import json
import logging
import os
import sys

import typer
from filelock import Timeout
from rich.console import Console

# Import `app` directly for decorator typing; use `cli` for patchable dependencies.
from ghstars import cli
from ghstars.cli import app
from ghstars.cli.errors import (
    CODE_NETWORK_FAILURE,
    CODE_RATE_LIMIT_EXCEEDED,
    CODE_STATE_LOCK_HELD,
    fail,
)
from ghstars.core import RateLimitExceededError, sync
from ghstars.github import GitHubApiError

_FETCHER_LOGGER_NAME = "ghstars.github"


@app.command("sync")
def sync_cmd(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Emit verbose fetcher debug logging (gh api calls, pagination, "
        "per-item progress) to stderr. Also honors GHSTARS_DEBUG=1.",
    ),
) -> None:
    """Fetch stars and Lists from GitHub into local state.

    `--json` emits one document holding the ordered stage labels
    `sync()` reported (`"stages"`) alongside the final `SyncResult`
    fields -- `star_count`, `list_count`, `failed_tag_pushes` (ticket 30
    Scope 5). Human progress (the spinner, or `--debug`'s stage lines)
    always goes to standard error, so it never corrupts the JSON on
    standard out.
    """
    client = cli.get_client()
    store = cli.get_store()
    # Treat any non-empty `GHSTARS_DEBUG` value as true without strict parsing.
    debug = debug or bool(os.environ.get("GHSTARS_DEBUG"))
    if debug:
        # Configure only the fetcher logger; do not enable unrelated loggers.
        fetcher_logger = logging.getLogger(_FETCHER_LOGGER_NAME)
        # Remove a prior command handler before adding a new one.
        for old_handler in list(fetcher_logger.handlers):
            if getattr(old_handler, "_ghstars_debug_handler", False):
                fetcher_logger.removeHandler(old_handler)
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
        handler._ghstars_debug_handler = True  # type: ignore[attr-defined]
        fetcher_logger.addHandler(handler)
        fetcher_logger.setLevel(logging.DEBUG)
        fetcher_logger.propagate = False

    # Write progress to stderr so JSON output remains clean.
    console = Console(stderr=True)
    stages: list[str] = []
    try:
        if debug:
            # Use plain stage lines so debug logs do not collide with the spinner.
            def _on_stage(stage: str) -> None:
                stages.append(stage)
                typer.echo(f"{stage}...", err=True)

            result = sync(client, store, on_stage=_on_stage)
        else:
            with console.status("Starting sync...", spinner="dots") as spinner:

                def _on_stage(stage: str) -> None:
                    stages.append(stage)
                    spinner.update(f"{stage}...")

                result = sync(client, store, on_stage=_on_stage)
    except RateLimitExceededError as exc:
        fail(str(exc), code=CODE_RATE_LIMIT_EXCEEDED, json_output=json_output)
    except GitHubApiError as exc:
        fail(str(exc), code=CODE_NETWORK_FAILURE, json_output=json_output)
    except Timeout:
        # Report lock contention without a traceback; no state was written.
        fail(
            "could not acquire the local state lock — another ghstars "
            "command may be running. Try again.",
            code=CODE_STATE_LOCK_HELD,
            json_output=json_output,
        )

    if json_output:
        payload = {"stages": stages, **result.model_dump(mode="json")}
        typer.echo(json.dumps(payload))
        return
    typer.echo(f"Synced {result.star_count} star(s), {result.list_count} list(s).")
    if result.failed_tag_pushes:
        names = ", ".join(result.failed_tag_pushes)
        typer.echo(
            f"warning: could not push pending tag(s) for: {names} "
            "(the repo may have been unstarred since it was tagged). "
            "Re-run `ghstars tag` if you still want it classified.",
            err=True,
        )
