import json

import typer
from pydantic import BaseModel

from ghstars.cli.deps import (
    check_stale_export_config,
    ensure_config_dir,
    get_cli_config_path,
    get_client,
    get_core_config_path,
    get_store,
    get_tui_config_path,
    get_tui_state_path,
)
from ghstars.cli.errors import fail
from ghstars.cli.git_diff import git_unavailable_reason
from ghstars.core.fields import select_fields

# Re-export dependencies so commands and tests can patch this package namespace.
__all__ = [
    "app",
    "category_app",
    "check_stale_export_config",
    "ensure_config_dir",
    "get_cli_config_path",
    "get_client",
    "get_core_config_path",
    "get_store",
    "get_tui_config_path",
    "get_tui_state_path",
    "git_unavailable_reason",
]

app = typer.Typer(no_args_is_help=True)
category_app = typer.Typer(
    no_args_is_help=True, help="Rename or bulk-migrate a Category across its Lists."
)
app.add_typer(category_app, name="category")


@app.callback()
def main() -> None:
    """ghstars: classify GitHub starred repos into GitHub's native Lists."""
    ensure_config_dir()
    check_stale_export_config()


def _render_records[ModelT: BaseModel](
    records: list[ModelT],
    *,
    field_names: set[str],
    default_fields: list[str],
    empty_message: str,
    json_output: bool,
    fields: str | None,
) -> None:
    """Shared `--json`/`--fields` rendering for list-returning commands.

    Contract (spec stories 28-30): `--json` gives structured output.
    `--fields` selects a subset, validated against `field_names`; an
    unknown field hard-fails via `fail()`. Otherwise, print plain text.

    Shared by `ghstars.cli.commands.list_lists` (`list`, `lists`) and
    `ghstars.cli.commands.retriage` (`retriage`) -- kept here, not in any
    one command module, per this package's own "shared helpers used by
    multiple command modules" mandate (ticket 19).
    """
    selected: list[str] | None = None
    if fields is not None:
        selected = [f.strip() for f in fields.split(",") if f.strip()]
        unknown = [f for f in selected if f not in field_names]
        if unknown:
            fail(f"unknown field(s): {', '.join(unknown)}")

    if json_output:
        # An empty --fields (e.g. --fields "" or --fields ",") filters to
        # nothing after stripping; treat it as "no restriction", matching
        # `display_fields = selected or default_fields` below.
        rows = [select_fields(record, selected or None) for record in records]
        typer.echo(json.dumps(rows))
        return

    if not records:
        typer.echo(empty_message)
        return

    display_fields = selected or default_fields
    for record in records:
        typer.echo(" ".join(str(getattr(record, f)) for f in display_fields))


# Import commands last so their decorators register all CLI commands.
from ghstars.cli import commands  # noqa: F401
