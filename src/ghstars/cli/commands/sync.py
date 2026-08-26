import json
import logging
import os
import sys

import typer
from filelock import Timeout
from rich.console import Console

# `app` is imported by name -- not just reached via `cli.app` -- so mypy
# can resolve its type for the `@app.command(...)` decorator below across
# the ghstars.cli <-> ghstars.cli.commands import cycle (this package is
# imported from ghstars/cli/__init__.py's own bottom, for registration).
# `cli.<name>` calls inside the function body below still resolve live
# against the `ghstars.cli` package itself, so a test's
# `monkeypatch.setattr(cli_module, "get_client", ...)` still reaches them.
from ghstars import cli
from ghstars.cli import app
from ghstars.cli.errors import fail
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
    """Fetch stars and Lists from GitHub into local state."""
    client = cli.get_client()
    store = cli.get_store()
    # Read the env var manually rather than via typer's `envvar=` -- that
    # goes through click's strict boolean parsing, so a non-boolean value
    # (e.g. GHSTARS_DEBUG=verbose) would crash the whole sync instead of
    # just falling back. Any non-empty value here is treated as truthy,
    # matching the help text ("Also honors GHSTARS_DEBUG=1").
    debug = debug or bool(os.environ.get("GHSTARS_DEBUG"))
    if debug:
        # Attach a handler to the fetcher logger only, and stop it from
        # propagating -- logging.basicConfig() would set the *root*
        # logger's level instead, which also turns on DEBUG for
        # unrelated third-party loggers (e.g. filelock logs 4 lines per
        # state-lock acquire/release, of which sync() does several).
        fetcher_logger = logging.getLogger(_FETCHER_LOGGER_NAME)
        # Drop any handler this command attached on a prior invocation in
        # the same process (e.g. repeated `runner.invoke()` calls in
        # tests) before adding a fresh one, so they don't pile up.
        for old_handler in list(fetcher_logger.handlers):
            if getattr(old_handler, "_ghstars_debug_handler", False):
                fetcher_logger.removeHandler(old_handler)
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
        handler._ghstars_debug_handler = True  # type: ignore[attr-defined]
        fetcher_logger.addHandler(handler)
        fetcher_logger.setLevel(logging.DEBUG)
        fetcher_logger.propagate = False

    # A sync can take minutes (one `gh` subprocess round trip per page,
    # per pending tag push -- see docs/explanation/known-limitations.md)
    # with nothing else written to the console in the meantime. stderr,
    # so a `--json` caller's stdout stays clean; Console degrades to
    # plain status lines instead of an animated spinner when stderr
    # isn't a terminal (e.g. piped/CI), rather than garbling output.
    console = Console(stderr=True)
    try:
        if debug:
            # The animated spinner and raw debug log lines both target
            # stderr; the spinner redraws its own line in place, which
            # garbles interleaved plain log output. Plain stage lines
            # instead, so --debug output stays readable top to bottom.
            def _on_stage(stage: str) -> None:
                typer.echo(f"{stage}...", err=True)

            result = sync(client, store, on_stage=_on_stage)
        else:
            with console.status("Starting sync...", spinner="dots") as spinner:
                result = sync(
                    client,
                    store,
                    on_stage=lambda stage: spinner.update(f"{stage}..."),
                )
    except (RateLimitExceededError, GitHubApiError) as exc:
        fail(str(exc))
    except Timeout:
        # A concurrent `ghstars` command already holds the state lock --
        # a clean error beats a raw traceback; nothing was written either
        # way (the lock never acquired). Same pattern as tag.py.
        fail(
            "could not acquire the local state lock — another ghstars "
            "command may be running. Try again."
        )

    if json_output:
        typer.echo(json.dumps(result.model_dump(mode="json")))
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
