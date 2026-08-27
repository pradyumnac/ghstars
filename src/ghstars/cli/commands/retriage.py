import typer

from ghstars import cli
from ghstars.cli import app  # imported by name for mypy; see commands/sync.py
from ghstars.core.fields import FIELD_REGISTRY
from ghstars.core.models import RetriageEntry

RETRIAGE_FIELDS = set(RetriageEntry.model_fields.keys())
DEFAULT_RETRIAGE_FIELDS = list(FIELD_REGISTRY["retriage"].basic)


@app.command("retriage")
def retriage_cmd(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    fields: str | None = typer.Option(
        None, "--fields", help="Comma-separated field names to include."
    ),
) -> None:
    """List Stars whose staged List-membership edit conflicted with a
    concurrent GitHub-side change at the last sync.

    GitHub always won that conflict (ADR 0001); the losing local edit
    was never applied and lives here for the user to revisit, e.g. by
    re-running `ghstars tag`. Local-only: never synced to GitHub, never
    a `UserList` (ticket 05).
    """
    entries = cli.get_store().load_retriage()
    cli._render_records(
        entries,
        field_names=RETRIAGE_FIELDS,
        default_fields=DEFAULT_RETRIAGE_FIELDS,
        empty_message="No conflicts to retriage.",
        json_output=json_output,
        fields=fields,
    )
