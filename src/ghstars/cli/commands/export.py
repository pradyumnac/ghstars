import json
from pathlib import Path

import typer

from ghstars import cli
from ghstars.cli import app  # imported by name for mypy; see commands/sync.py
from ghstars.cli.errors import CODE_INVALID_INPUT, fail
from ghstars.core import CoreConfigError, load_core_config, run_export


@app.command("export")
def export_cmd(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Write local Stars out to file(s), per the `[export]` table of
    `~/.ghstars/config/ghstars.toml`.

    Generic and config-driven (ticket 10): each entry in `[export]`
    maps a List or Category to an output file + format. ghstars ships no
    hardcoded exporter for any particular downstream use case (e.g. a
    `tools.yaml` for a dotfiles pipeline) — those are example config, not
    special-cased code paths. Output paths are resolved relative to the
    current working directory unless absolute, so running this from
    inside the target repo is the expected workflow.
    """
    store = cli.get_store()
    try:
        config = load_core_config(cli.get_core_config_path()).export
    except CoreConfigError as exc:
        fail(str(exc), code=CODE_INVALID_INPUT, json_output=json_output)

    if not config.exports:
        if json_output:
            typer.echo(json.dumps([]))
            return
        typer.echo(
            "No exports configured. Add [[export.exports]] entries to "
            f"{cli.get_core_config_path()} (see docs/how-to/export.md)."
        )
        return

    results = run_export(
        config,
        lists=store.load_lists(),
        stars=store.load_stars(),
        base_dir=Path.cwd(),
    )

    if json_output:
        typer.echo(json.dumps([result.model_dump(mode="json") for result in results]))
        return

    for result in results:
        typer.echo(
            f"Wrote {result.star_count} star(s) to {result.output} ({result.format})."
        )
        if result.skipped_malformed_lists:
            names = ", ".join(result.skipped_malformed_lists)
            typer.echo(
                f"warning: export {result.name!r} skipped malformed "
                f"List(s), never guessed at: {names}. Rename them on "
                "GitHub, then re-run `ghstars sync`.",
                err=True,
            )
