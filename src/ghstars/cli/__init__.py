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
from ghstars.cli.errors import CODE_UNKNOWN_FIELD, fail
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
    basic_fields: list[str],
    detailed_fields: list[str],
    empty_message: str,
    json_output: bool,
    fields: str | None,
    details: bool = False,
    total: int | None = None,
    offset: int = 0,
    limit: int | None = None,
) -> None:
    """Shared `--json`/`--fields`/`--details` rendering for every
    list-returning command (ticket 30 Scope 2).

    `--json` emits one envelope: `{"total", "offset", "limit", "rows"}`
    (Decision 19). `total` is the caller's own count of matching records
    before any page was sliced off -- `records` here is already the page
    to render, so a caller with pagination (`ghstars stars`) passes its own
    pre-slice count; a caller without it (`github-lists`, `retriage`) leaves
    `total` as `None`, in which case it defaults to `len(records)`.
    `offset`/`limit` default to `0`/`None`, matching an unbounded,
    unpaged command (Decision 20).

    `--fields` selects an arbitrary subset, validated against
    `field_names`, and overrides `basic_fields`/`detailed_fields` alike.
    `--details` selects `detailed_fields` over `basic_fields` when
    `--fields` is absent (Decision 8/17). JSON and text render the same
    selected fields, in the same order -- only the format differs
    (`select_fields` is the one field-selection code path for both).

    Text mode: the basic set prints as an aligned table (Decision 8);
    `--details` prints one key-value block per record, blank-line
    separated, since a wide detailed set does not fit a table column
    (Decision 17).

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
            fail(
                f"unknown field(s): {', '.join(unknown)}",
                code=CODE_UNKNOWN_FIELD,
                json_output=json_output,
                target=", ".join(unknown),
            )

    # An empty --fields (e.g. --fields "" or --fields ",") strips to no
    # field names; treat that the same as --fields being absent, not as
    # an explicit empty selection.
    display_fields = selected or (detailed_fields if details else basic_fields)
    rows = [select_fields(record, display_fields) for record in records]

    if json_output:
        envelope = {
            "total": total if total is not None else len(records),
            "offset": offset,
            "limit": limit,
            "rows": rows,
        }
        typer.echo(json.dumps(envelope))
        return

    if not records:
        typer.echo(empty_message)
        return

    if details:
        for index, row in enumerate(rows):
            if index:
                typer.echo("")
            for field in display_fields:
                typer.echo(f"{field}: {row[field]}")
        return

    widths = {
        field: max(len(field), *(len(str(row[field])) for row in rows))
        for field in display_fields
    }

    def _padded(cell: str, field: str, is_last: bool) -> str:
        return cell if is_last else cell.ljust(widths[field])

    last = display_fields[-1]
    typer.echo(
        "  ".join(_padded(field, field, field == last) for field in display_fields)
    )
    for row in rows:
        typer.echo(
            "  ".join(
                _padded(str(row[field]), field, field == last)
                for field in display_fields
            )
        )


# Import commands last so their decorators register all CLI commands.
from ghstars.cli import commands  # noqa: F401
