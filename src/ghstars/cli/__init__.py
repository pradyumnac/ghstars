import json

import typer
from pydantic import BaseModel

from ghstars.cli.deps import (
    ensure_config_dir,
    get_client,
    get_export_config_path,
    get_store,
)
from ghstars.cli.errors import fail
from ghstars.cli.git_diff import git_unavailable_reason

# Re-exported so `ghstars.cli.commands.*` can reach these through this
# package's own namespace (`import ghstars.cli as cli; cli.get_store()`,
# etc.), not by importing them directly into a command module's own
# globals -- tests monkeypatch these by name *on this module*
# (`monkeypatch.setattr(cli_module, "get_store", ...)`, `tests/test_cli.py`
# et al.), and a direct `from ghstars.cli.deps import get_store` in a
# command module would copy the original binding at import time, deaf to
# that monkeypatch. `app`/`category_app` need no such indirection --
# never reassigned, only ever built once, right here.
__all__ = [
    "app",
    "category_app",
    "ensure_config_dir",
    "get_client",
    "get_export_config_path",
    "get_store",
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
        rows = [
            record.model_dump(mode="json", include=set(selected) if selected else None)
            for record in records
        ]
        typer.echo(json.dumps(rows))
        return

    if not records:
        typer.echo(empty_message)
        return

    display_fields = selected or default_fields
    for record in records:
        typer.echo(" ".join(str(getattr(record, f)) for f in display_fields))


# Imported last, and only for its side effect: each `ghstars.cli.commands.*`
# module registers its command(s) on `app`/`category_app` (both already
# built above) via `@app.command(...)`/`@category_app.command(...)` at
# import time. Mirrors how `ghstars.core.__init__` re-exports its
# submodules' names -- this package re-exports registrations instead.
from ghstars.cli import commands  # noqa: F401
