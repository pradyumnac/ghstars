from typing import cast

import typer

from ghstars import cli
from ghstars.cli import app  # imported by name for mypy; see commands/sync.py
from ghstars.cli.errors import CODE_INVALID_INPUT, fail
from ghstars.core.discovery import SortMode, query_stars
from ghstars.core.fields import FIELD_REGISTRY, StarRowFields
from ghstars.core.models import List

STAR_ROW_FIELDS = set(FIELD_REGISTRY["star_row"].detailed)
BASIC_STAR_ROW_FIELDS = list(FIELD_REGISTRY["star_row"].basic)
DETAILED_STAR_ROW_FIELDS = list(FIELD_REGISTRY["star_row"].detailed)

LIST_FIELDS = set(FIELD_REGISTRY["list"].detailed)
BASIC_LISTS_FIELDS = list(FIELD_REGISTRY["list"].basic)
DETAILED_LISTS_FIELDS = list(FIELD_REGISTRY["list"].detailed)

# Ticket 30 Decision 14. Ticket 32 Scope 3 later moves this into `cli.toml`.
DEFAULT_LIST_LIMIT = 50

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


@app.command("stars")
def stars_cmd(
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
    limit: int = typer.Option(
        DEFAULT_LIST_LIMIT, "--limit", help="Maximum rows to return."
    ),
    offset: int = typer.Option(
        0, "--offset", help="Skip this many matching rows before applying --limit."
    ),
    details: bool = typer.Option(
        False, "--details", help="Use the detailed field set instead of the basic one."
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    fields: str | None = typer.Option(
        None, "--fields", help="Comma-separated field names to include."
    ),
) -> None:
    """List locally synced Stars, filtered, searched, and sorted through the
    same query core.discovery and the TUI use.

    Named `stars`, not `list`, to keep it unambiguous next to the
    `github-lists` command: this returns Star rows, that returns GitHub
    List rows (ticket 30 Scope 7, Decision 26).

    Filters combine with AND. Every repeated `--category`/`--intent`/etc.
    option adds one more AND'd Filter, matching `core.discovery`'s grammar.

    Capped at `--limit` rows (default 50), starting at `--offset`
    (Decisions 2/14/20). Paging is deterministic only while local state is:
    a `ghstars sync` between two paged calls can insert or remove rows
    ahead of a later offset and shift it (Decision 21). Run `ghstars sync`
    first, then page through one static snapshot.
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
    matched = query_stars(
        store.load_stars(),
        store.load_lists(),
        filters=filters,
        search=search,
        sort=cast(SortMode, sort),
        include_archived=include_archived,
    )
    total = len(matched)
    page = matched[offset : offset + limit]
    star_rows = [
        StarRowFields(**row.star.model_dump(), list_names=row.list_names)
        for row in page
    ]

    basic_fields = BASIC_STAR_ROW_FIELDS
    if include_archived and "archived" not in basic_fields:
        basic_fields = [*BASIC_STAR_ROW_FIELDS, "archived"]

    cli._render_records(
        star_rows,
        field_names=STAR_ROW_FIELDS,
        basic_fields=basic_fields,
        detailed_fields=DETAILED_STAR_ROW_FIELDS,
        empty_message="No stars synced yet. Run `ghstars sync` first.",
        json_output=json_output,
        fields=fields,
        details=details,
        total=total,
        offset=offset,
        limit=limit,
    )


@app.command("github-lists")
def github_lists_cmd(
    details: bool = typer.Option(
        False, "--details", help="Use the detailed field set instead of the basic one."
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    fields: str | None = typer.Option(
        None, "--fields", help="Comma-separated field names to include."
    ),
) -> None:
    """List locally synced GitHub Lists, with parsed Intent/Category.

    Named `github-lists`, not `lists`, to keep it unambiguous next to the
    `stars` command: this returns GitHub List rows, that returns Star rows
    (ticket 30 Scope 7, Decision 26).

    Bounded output: no `--limit`, no `--offset` (Decision 20).
    """
    lists: list[List] = cli.get_store().load_lists()
    cli._render_records(
        lists,
        field_names=LIST_FIELDS,
        basic_fields=BASIC_LISTS_FIELDS,
        detailed_fields=DETAILED_LISTS_FIELDS,
        empty_message="No Lists synced yet. Run `ghstars sync` first.",
        json_output=json_output,
        fields=fields,
        details=details,
    )
