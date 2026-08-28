import typer

from ghstars import cli
from ghstars.cli import app  # imported by name for mypy; see commands/sync.py
from ghstars.core.fields import FIELD_REGISTRY

RETRIAGE_FIELDS = set(FIELD_REGISTRY["retriage"].detailed)
BASIC_RETRIAGE_FIELDS = list(FIELD_REGISTRY["retriage"].basic)
DETAILED_RETRIAGE_FIELDS = list(FIELD_REGISTRY["retriage"].detailed)


@app.command("retriage")
def retriage_cmd(
    details: bool = typer.Option(
        False, "--details", help="Use the detailed field set instead of the basic one."
    ),
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
    a `UserList` (ticket 05). Bounded output: no `--limit`, no `--offset`
    (Decision 20).
    """
    entries = cli.get_store().load_retriage()
    cli._render_records(
        entries,
        field_names=RETRIAGE_FIELDS,
        basic_fields=BASIC_RETRIAGE_FIELDS,
        detailed_fields=DETAILED_RETRIAGE_FIELDS,
        empty_message="No conflicts to retriage.",
        json_output=json_output,
        fields=fields,
        details=details,
    )
