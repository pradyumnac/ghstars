from typing import cast

import typer

from ghstars import cli
from ghstars.cli import app  # imported by name for mypy; see commands/sync.py
from ghstars.cli.errors import CODE_INVALID_INPUT, fail
from ghstars.core.discovery import SortMode, query_stars
from ghstars.core.fields import FIELD_REGISTRY
from ghstars.core.models import List, Star

STAR_FIELDS = set(Star.model_fields.keys())
DEFAULT_STAR_FIELDS = list(FIELD_REGISTRY["star"].basic)

LIST_FIELDS = set(List.model_fields.keys())
DEFAULT_LISTS_FIELDS = list(FIELD_REGISTRY["list"].basic)

_CATEGORY_OPTION = typer.Option(
    None, "--category", help="Only Stars in a List of this Category. Repeatable."
)
_INTENT_OPTION = typer.Option(
    None, "--intent", help="Only Stars in a List with this Intent. Repeatable."
)
_LIST_OPTION = typer.Option(
    None, "--list", help="Only Stars in this exact List id. Repeatable."
)
_LANGUAGE_OPTION = typer.Option(
    None,
    "--language",
    help="Only Stars whose primary language matches. Repeatable.",
)
_LICENSE_OPTION = typer.Option(
    None, "--license", help="Only Stars whose license matches. Repeatable."
)
_OWNER_OPTION = typer.Option(
    None, "--owner", help="Only Stars owned by this account. Repeatable."
)

_SORT_MODES: set[str] = {
    "name_asc",
    "name_desc",
    "starred_asc",
    "starred_desc",
    "stargazer_asc",
    "stargazer_desc",
    "language_asc",
    "language_desc",
    "list_count_asc",
    "list_count_desc",
    "list_name_asc",
    "list_name_desc",
}


@app.command("list")
def list_cmd(
    category: list[str] | None = _CATEGORY_OPTION,
    intent: list[str] | None = _INTENT_OPTION,
    list_id: list[str] | None = _LIST_OPTION,
    language: list[str] | None = _LANGUAGE_OPTION,
    license_: list[str] | None = _LICENSE_OPTION,
    owner: list[str] | None = _OWNER_OPTION,
    fork: bool = typer.Option(False, "--fork", help="Only forks."),
    followed: bool = typer.Option(
        False, "--followed", help="Only Stars whose owner is followed."
    ),
    unclassified: bool = typer.Option(
        False, "--unclassified", help="Only Stars that belong to no List."
    ),
    recent: str | None = typer.Option(
        None,
        "--recent",
        help="Only Stars starred within this window: 1d, 1w, 1m, 3m, 1y, or older_1y.",
    ),
    search: str = typer.Option(
        "", "--search", help="Case-insensitive substring match on name/description."
    ),
    sort: str = typer.Option(
        "starred_desc",
        "--sort",
        help="Sort mode, e.g. starred_desc, name_asc, stargazer_desc.",
    ),
    include_archived: bool = typer.Option(
        False, "--include-archived", help="Include Archived Stars, excluded by default."
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    fields: str | None = typer.Option(
        None, "--fields", help="Comma-separated field names to include."
    ),
) -> None:
    """List locally synced stars, filtered, searched, and sorted through the
    same query core.discovery and the TUI use.

    Filters combine with AND. Every repeated `--category`/`--intent`/etc.
    option adds one more AND'd Filter, matching `core.discovery`'s grammar.
    """
    if sort not in _SORT_MODES:
        fail(
            f"unknown sort mode: {sort!r}",
            code=CODE_INVALID_INPUT,
            json_output=json_output,
            target=sort,
        )

    filters: list[str] = [
        *(f"category:{value}" for value in category or []),
        *(f"intent:{value}" for value in intent or []),
        *(f"list:{value}" for value in list_id or []),
        *(f"language:{value}" for value in language or []),
        *(f"license:{value}" for value in license_ or []),
        *(f"owner:{value}" for value in owner or []),
    ]
    if fork:
        filters.append("forks")
    if followed:
        filters.append("followed")
    if unclassified:
        filters.append("unclassified")
    if recent:
        filters.append(f"recent:{recent}")

    store = cli.get_store()
    rows = query_stars(
        store.load_stars(),
        store.load_lists(),
        filters=filters,
        search=search,
        sort=cast(SortMode, sort),
        include_archived=include_archived,
    )
    stars = [row.star for row in rows]

    default_fields = DEFAULT_STAR_FIELDS
    if include_archived and "archived" not in default_fields:
        default_fields = [*DEFAULT_STAR_FIELDS, "archived"]

    cli._render_records(
        stars,
        field_names=STAR_FIELDS,
        default_fields=default_fields,
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
