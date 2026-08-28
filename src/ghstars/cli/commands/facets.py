import json

import typer

from ghstars import cli
from ghstars.cli import app  # imported by name for mypy; see commands/sync.py
from ghstars.core.discovery import available_facets


@app.command("facets")
def facets_cmd(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Show the Category, Intent, List, language, license, and owner values
    an agent can filter `ghstars stars` on, read from the caller's own
    synced data (Decision 25).
    """
    store = cli.get_store()
    facets = available_facets(store.load_stars(), store.load_lists())

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "categories": facets.categories,
                    "intents": facets.intents,
                    "lists": [lst.model_dump(mode="json") for lst in facets.lists],
                    "languages": facets.languages,
                    "licenses": facets.licenses,
                    "owners": facets.owners,
                }
            )
        )
        return

    if facets.categories:
        typer.echo("Categories: " + ", ".join(facets.categories))
    if facets.intents:
        typer.echo("Intents: " + ", ".join(facets.intents))
    if facets.lists:
        typer.echo("Lists:")
        for lst in facets.lists:
            typer.echo(f"  {lst.id}  {lst.name}")
    if facets.languages:
        typer.echo("Languages: " + ", ".join(facets.languages))
    if facets.licenses:
        typer.echo("Licenses: " + ", ".join(facets.licenses))
    if facets.owners:
        typer.echo("Owners: " + ", ".join(facets.owners))
