import json
from typing import NoReturn

import typer
from filelock import Timeout

from ghstars import cli
from ghstars.cli import category_app  # imported by name for mypy; see commands/sync.py
from ghstars.cli.errors import (
    CODE_INVALID_INPUT,
    CODE_NETWORK_FAILURE,
    CODE_NO_LOCAL_RECORD,
    CODE_STATE_LOCK_HELD,
    fail,
)
from ghstars.core import (
    CategoryNotFoundError,
    InvalidCategoryNameError,
    drain_category,
    rename_category,
)
from ghstars.github import GitHubApiError


def _category_not_found(category: str, *, json_output: bool) -> NoReturn:
    fail(
        f"no Explore/Current/Retired List found for category {category!r}. "
        "Run `ghstars sync` first, or check for a typo.",
        code=CODE_NO_LOCAL_RECORD,
        json_output=json_output,
        target=category,
    )


def _lock_timeout(*, json_output: bool) -> NoReturn:
    fail(
        "could not acquire the local state lock — another ghstars "
        "command may be running. Try again.",
        code=CODE_STATE_LOCK_HELD,
        json_output=json_output,
    )


@category_app.command("rename")
def category_rename_cmd(
    old: str = typer.Argument(..., help="Existing Category name, e.g. 'Old Tool'."),
    new: str = typer.Argument(..., help="New Category name to rename it to."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Rename a Category across its Explore/Current/Retired Lists.

    Renames every Explore/Current/Retired List for `old` to the same
    Intent under `new`, consistently, in one operation (ticket 07).
    Fetches fresh GitHub state right before writing and skips (reports,
    never overwrites) any List whose live state has already diverged
    from the last `ghstars sync` — e.g. renamed or reclassified
    concurrently on github.com or the phone app.
    """
    # Normalize names so messages match the values used for lookup.
    old = old.strip()
    new = new.strip()
    client = cli.get_client()
    store = cli.get_store()
    try:
        result = rename_category(client, store, old, new)
    except InvalidCategoryNameError as exc:
        fail(str(exc), code=CODE_INVALID_INPUT, json_output=json_output)
    except CategoryNotFoundError:
        _category_not_found(old, json_output=json_output)
    except GitHubApiError as exc:
        fail(str(exc), code=CODE_NETWORK_FAILURE, json_output=json_output)
    except Timeout:
        _lock_timeout(json_output=json_output)

    if json_output:
        typer.echo(json.dumps(result.model_dump(mode="json")))
        return
    typer.echo(f"Renamed {len(result.renamed)} List(s) from {old!r} to {new!r}.")
    if result.skipped:
        ids = ", ".join(result.skipped)
        typer.echo(
            f"warning: skipped {len(result.skipped)} List(s) whose live state "
            f"already diverged since the last sync: {ids}. Run `ghstars sync` "
            "then retry if you still want them renamed.",
            err=True,
        )


@category_app.command("drain")
def category_drain_cmd(
    from_category: str = typer.Argument(..., help="Category to migrate Stars out of."),
    to_category: str = typer.Argument(..., help="Category to migrate Stars into."),
    private: bool = typer.Option(
        False,
        "--private",
        help="Create any destination List private if it doesn't exist yet "
        "(default: public).",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Bulk-migrate every Star from one Category into another.

    Migrates each Star into the same lifecycle Intent under
    `to_category` it already held under `from_category` — Explore stays
    Explore, Current stays Current, Retired stays Retired (ticket 07).
    Fetches fresh GitHub state right before writing and skips (reports,
    never overwrites) any Star whose live List membership has already
    diverged from the last `ghstars sync`.
    """
    # Normalize names before lookup and reporting.
    from_category = from_category.strip()
    to_category = to_category.strip()
    client = cli.get_client()
    store = cli.get_store()
    try:
        result = drain_category(
            client, store, from_category, to_category, is_private=private
        )
    except InvalidCategoryNameError as exc:
        fail(str(exc), code=CODE_INVALID_INPUT, json_output=json_output)
    except CategoryNotFoundError:
        _category_not_found(from_category, json_output=json_output)
    except GitHubApiError as exc:
        fail(str(exc), code=CODE_NETWORK_FAILURE, json_output=json_output)
    except Timeout:
        _lock_timeout(json_output=json_output)

    if json_output:
        typer.echo(json.dumps(result.model_dump(mode="json")))
        return
    typer.echo(
        f"Migrated {len(result.migrated)} Star(s) from "
        f"{from_category!r} to {to_category!r}."
    )
    if result.skipped:
        names = ", ".join(result.skipped)
        typer.echo(
            f"warning: skipped {len(result.skipped)} Star(s) whose live List "
            f"membership already diverged since the last sync: {names}. Run "
            "`ghstars sync` then retry if you still want them migrated.",
            err=True,
        )
