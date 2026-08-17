import json
from datetime import UTC, datetime
from typing import NoReturn

import typer
from pydantic import BaseModel

from ghstars.cli.deps import ensure_config_dir, get_client, get_store
from ghstars.cli.errors import fail
from ghstars.core import (
    CategoryNotFoundError,
    InvalidCategoryNameError,
    RateLimitExceededError,
    StarArchivedError,
    StarNotFoundError,
    archive_star,
    drain_category,
    remove_star_from_lists,
    rename_category,
    sync,
    tag_star,
)
from ghstars.core.models import List, RetriageEntry, Star
from ghstars.github import GitHubApiError

app = typer.Typer(no_args_is_help=True)
category_app = typer.Typer(
    no_args_is_help=True, help="Rename or bulk-migrate a Category across its Lists."
)
app.add_typer(category_app, name="category")

STAR_FIELDS = set(Star.model_fields.keys())
DEFAULT_STAR_FIELDS = ["full_name", "language", "stargazer_count"]

LIST_FIELDS = set(List.model_fields.keys())
DEFAULT_LISTS_FIELDS = ["name", "intent", "category", "is_private", "malformed"]

RETRIAGE_FIELDS = set(RetriageEntry.model_fields.keys())
DEFAULT_RETRIAGE_FIELDS = [
    "star_full_name",
    "attempted_list_ids",
    "conflict_detected_at",
    "resolved",
]


@app.callback()
def main() -> None:
    """ghstars: classify GitHub starred repos into GitHub's native Lists."""
    ensure_config_dir()


@app.command("sync")
def sync_cmd(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Fetch stars and Lists from GitHub into local state."""
    client = get_client()
    store = get_store()
    try:
        result = sync(client, store)
    except (RateLimitExceededError, GitHubApiError) as exc:
        fail(str(exc))

    if json_output:
        typer.echo(json.dumps(result.model_dump(mode="json")))
        return
    typer.echo(f"Synced {result.star_count} star(s), {result.list_count} list(s).")
    if result.failed_tag_pushes:
        names = ", ".join(result.failed_tag_pushes)
        typer.echo(
            f"warning: could not push pending tag(s) for: {names} "
            "(the repo may have been unstarred since it was tagged). "
            "Re-run `ghstars tag` if you still want it classified.",
            err=True,
        )
    if result.failed_default_pushes:
        names = ", ".join(result.failed_default_pushes)
        typer.echo(
            f"warning: could not push default classification for: {names} "
            "(the repo or the 'Explore: General' List may have changed "
            "concurrently). Re-run `ghstars sync` to retry.",
            err=True,
        )


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


@app.command("list")
def list_cmd(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    fields: str | None = typer.Option(
        None, "--fields", help="Comma-separated field names to include."
    ),
) -> None:
    """List locally synced stars."""
    stars = get_store().load_stars()
    _render_records(
        stars,
        field_names=STAR_FIELDS,
        default_fields=DEFAULT_STAR_FIELDS,
        empty_message="No stars synced yet. Run `ghstars sync` first.",
        json_output=json_output,
        fields=fields,
    )


@app.command("unstar")
def unstar_cmd(
    repo: str = typer.Argument(
        ..., help="Full name of the starred repo to unstar, e.g. owner/repo."
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Unstar a repo on GitHub for real, then mark its local record Archived.

    A real, visible mutation on the user's GitHub account (spec story 8).
    The local record is never deleted; it is kept and marked Archived
    (spec story 6), distinct from a List's Retired Intent (CONTEXT.md).
    """
    client = get_client()
    store = get_store()
    try:
        client.remove_star(repo)
    except GitHubApiError as exc:
        fail(str(exc))

    # The GitHub-side unstar already succeeded. Hold the lock across this
    # read-modify-write so a concurrent `ghstars sync` cannot clobber it
    # (spec story 33), same as sync()'s locked span.
    now = datetime.now(UTC)
    with store.lock():
        stars = store.load_stars()
        found_locally = any(star.full_name == repo for star in stars)
        updated = [
            archive_star(star, now=now)
            if star.full_name == repo and not star.archived
            else star
            for star in stars
        ]
        store.save_stars(updated)
        store.save_lists(remove_star_from_lists(store.load_lists(), repo))

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "full_name": repo,
                    "unstarred": True,
                    "archived_locally": found_locally,
                }
            )
        )
        return
    if found_locally:
        typer.echo(f"Unstarred {repo}.")
    else:
        typer.echo(
            f"Unstarred {repo} on GitHub (no local record to archive — "
            "run `ghstars sync` to pick it up)."
        )


@app.command("tag")
def tag_cmd(
    repo: str = typer.Argument(
        ..., help="Full name of the starred repo to tag, e.g. owner/repo."
    ),
    list_name: str = typer.Argument(
        ..., help="Name of the List to add it to, e.g. 'Explore: Tool'."
    ),
    private: bool = typer.Option(
        False,
        "--private",
        help="Create the List private if it doesn't exist yet (default: public).",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Stage a repo for addition to a List. Run `ghstars sync` to push it.

    A new List is created for real immediately (spec story 48); the
    Star<->List membership itself is staged locally and pushed at the
    next sync, so a concurrent GitHub-side change has something to be
    checked against (ticket 05).
    """
    client = get_client()
    store = get_store()
    try:
        result = tag_star(client, store, repo, list_name, is_private=private)
    except StarNotFoundError:
        fail(f"no local record for {repo!r}. Run `ghstars sync` first.")
    except StarArchivedError:
        fail(f"{repo!r} is Archived (unstarred) locally — nothing to tag.")
    except GitHubApiError as exc:
        fail(str(exc))

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "full_name": repo,
                    "pending_list_ids": result.star.pending_list_ids,
                    "removed_list_ids": result.removed_list_ids,
                }
            )
        )
        return
    message = f"Staged {repo} for {list_name!r}. Run `ghstars sync` to push it."
    if result.removed_list_ids:
        message += f" (removed from {len(result.removed_list_ids)} other List(s))"
    typer.echo(message)


@app.command("lists")
def lists_cmd(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    fields: str | None = typer.Option(
        None, "--fields", help="Comma-separated field names to include."
    ),
) -> None:
    """List locally synced GitHub Lists, with parsed Intent/Category."""
    lists = get_store().load_lists()
    _render_records(
        lists,
        field_names=LIST_FIELDS,
        default_fields=DEFAULT_LISTS_FIELDS,
        empty_message="No Lists synced yet. Run `ghstars sync` first.",
        json_output=json_output,
        fields=fields,
    )


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
    entries = get_store().load_retriage()
    _render_records(
        entries,
        field_names=RETRIAGE_FIELDS,
        default_fields=DEFAULT_RETRIAGE_FIELDS,
        empty_message="No conflicts to retriage.",
        json_output=json_output,
        fields=fields,
    )


def _category_not_found(category: str) -> NoReturn:
    fail(
        f"no Explore/Current/Retired List found for category {category!r}. "
        "Run `ghstars sync` first, or check for a typo."
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
    # Stripped up front so every message below (success, skip warning,
    # not-found) reports the same normalized name `rename_category()`
    # actually matched against, not the raw (possibly whitespace-padded)
    # CLI argument.
    old = old.strip()
    new = new.strip()
    client = get_client()
    store = get_store()
    try:
        result = rename_category(client, store, old, new)
    except InvalidCategoryNameError as exc:
        fail(str(exc))
    except CategoryNotFoundError:
        _category_not_found(old)
    except GitHubApiError as exc:
        fail(str(exc))

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
    # Stripped up front, same reasoning as category_rename_cmd above.
    from_category = from_category.strip()
    to_category = to_category.strip()
    client = get_client()
    store = get_store()
    try:
        result = drain_category(
            client, store, from_category, to_category, is_private=private
        )
    except InvalidCategoryNameError as exc:
        fail(str(exc))
    except CategoryNotFoundError:
        _category_not_found(from_category)
    except GitHubApiError as exc:
        fail(str(exc))

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
