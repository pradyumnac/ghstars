import json
from datetime import UTC, datetime

import typer
from pydantic import BaseModel

from ghstars.cli.deps import ensure_config_dir, get_client, get_store
from ghstars.cli.errors import fail
from ghstars.cli.git_diff import (
    GitUnavailableError,
    git_unavailable_reason,
    run_git_diff,
)
from ghstars.core import (
    RateLimitExceededError,
    StarArchivedError,
    StarNotFoundError,
    archive_star,
    remove_star_from_lists,
    sync,
    tag_star,
)
from ghstars.core.models import List, RetriageEntry, Star
from ghstars.github import GitHubApiError

app = typer.Typer(no_args_is_help=True)

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


_DIFF_ARGS_OPTION = typer.Argument(
    None,
    help="Extra arguments passed through to git, e.g. a revision or path.",
)


@app.command(
    "diff",
    context_settings={"ignore_unknown_options": True},
    help="Show classification changes in state/, via the user's own git history.",
)
def diff_cmd(
    args: list[str] | None = _DIFF_ARGS_OPTION,
    log: bool = typer.Option(
        False,
        "--log",
        help="Show commit history (`git log -p`) instead of the working-tree "
        "diff (`git diff`).",
    ),
) -> None:
    """Wrap `git diff`/`git log -p` against `state/`'s own git repo.

    ghstars never runs `git init` on `state/` and never commits to it (ADR
    0002) -- this only works if the user has git-tracked `state/`
    themselves, e.g. as part of a dotfiles repo. No bespoke diff engine:
    this shells out to the user's own `git` and shows its output verbatim.
    """
    state_dir = get_store().base_dir
    reason = git_unavailable_reason(state_dir)
    if reason is not None:
        fail(
            f"no git history available for {state_dir} ({reason}). ghstars "
            "never runs `git init` or commits state/ on its own -- track it "
            "yourself (`git init` and commit inside that directory) if you "
            "want `ghstars diff`."
        )

    try:
        result = run_git_diff(state_dir, log=log, extra_args=args or [])
    except GitUnavailableError as exc:
        fail(f"{exc} while running `git diff`/`git log -p`.")

    if result.stdout:
        typer.echo(result.stdout, nl=False)
    if result.returncode != 0:
        if result.stderr:
            typer.echo(result.stderr, err=True, nl=False)
        raise typer.Exit(code=result.returncode)
