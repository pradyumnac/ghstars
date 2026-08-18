import json

import typer
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


@app.command("sync")
def sync_cmd(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Fetch stars and Lists from GitHub into local state."""
    client = cli.get_client()
    store = cli.get_store()
    # A sync can take minutes (one `gh` subprocess round trip per page,
    # per pending tag push -- see docs/explanation/known-limitations.md)
    # with nothing else written to the console in the meantime. stderr,
    # so a `--json` caller's stdout stays clean; Console degrades to
    # plain status lines instead of an animated spinner when stderr
    # isn't a terminal (e.g. piped/CI), rather than garbling output.
    console = Console(stderr=True)
    try:
        with console.status("Starting sync...", spinner="dots") as spinner:
            result = sync(
                client, store, on_stage=lambda stage: spinner.update(f"{stage}...")
            )
    except (RateLimitExceededError, GitHubApiError) as exc:
        fail(str(exc))

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
    if result.failed_default_pushes:
        names = ", ".join(result.failed_default_pushes)
        typer.echo(
            f"warning: could not push default classification for: {names} "
            "(the repo or the 'Explore: General' List may have changed "
            "concurrently). Re-run `ghstars sync` to retry.",
            err=True,
        )
