import json

import typer

from ghstars import cli
from ghstars.cli import taxonomy_app  # imported by name for mypy
from ghstars.cli.errors import CODE_INVALID_INPUT, fail
from ghstars.core.vocabulary import BlessError, bless_category


@taxonomy_app.command("bless")
def bless_cmd(
    category: str = typer.Argument(..., help="Category to add, e.g. 'AI Agents'."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Add a Category to `[taxonomy]` in `ghstars.toml`.

    The one place ghstars writes `config/`, and only because you asked
    (ADR 0002 as amended by ADR 0005). `tomlkit` round-trips the file, so
    comments and formatting survive.

    Idempotent, and normalizing: an underscore reads as a space, so
    blessing `AI_Agents` blesses `AI Agents`.
    """
    try:
        blessed = bless_category(cli.get_core_config_path(), category)
    except BlessError as exc:
        fail(str(exc), code=CODE_INVALID_INPUT, json_output=json_output)

    if json_output:
        typer.echo(
            json.dumps({"category": blessed, "path": str(cli.get_core_config_path())})
        )
        return
    typer.echo(f"Blessed {blessed!r} in {cli.get_core_config_path()}.")
