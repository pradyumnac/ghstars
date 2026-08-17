import typer

from ghstars import cli
from ghstars.cli import app  # imported by name for mypy; see commands/sync.py
from ghstars.core.models import List, Star

STAR_FIELDS = set(Star.model_fields.keys())
DEFAULT_STAR_FIELDS = ["full_name", "language", "stargazer_count"]

LIST_FIELDS = set(List.model_fields.keys())
DEFAULT_LISTS_FIELDS = ["name", "intent", "category", "is_private", "malformed"]


@app.command("list")
def list_cmd(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    fields: str | None = typer.Option(
        None, "--fields", help="Comma-separated field names to include."
    ),
) -> None:
    """List locally synced stars."""
    stars = cli.get_store().load_stars()
    cli._render_records(
        stars,
        field_names=STAR_FIELDS,
        default_fields=DEFAULT_STAR_FIELDS,
        empty_message="No stars synced yet. Run `ghstars sync` first.",
        json_output=json_output,
        fields=fields,
    )


@app.command("lists")
def lists_cmd(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    fields: str | None = typer.Option(
        None, "--fields", help="Comma-separated field names to include."
    ),
) -> None:
    """List locally synced GitHub Lists, with parsed Intent/Category."""
    lists = cli.get_store().load_lists()
    cli._render_records(
        lists,
        field_names=LIST_FIELDS,
        default_fields=DEFAULT_LISTS_FIELDS,
        empty_message="No Lists synced yet. Run `ghstars sync` first.",
        json_output=json_output,
        fields=fields,
    )
