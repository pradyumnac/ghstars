import json

import typer

from ghstars import cli
from ghstars.cli import remote_app  # imported by name for mypy; see commands/sync.py
from ghstars.cli.errors import CODE_INVALID_INPUT, CODE_NETWORK_FAILURE, fail
from ghstars.core import CoreConfigError, load_core_config
from ghstars.core.doctor import (
    ListNameTakenError,
    ListNotFoundError,
    bootstrap_lists,
    diagnose,
    planned_creates,
    rename_list,
)
from ghstars.core.models import Intent
from ghstars.core.taxonomy import UnwritableListNameError
from ghstars.github import GitHubApiError

_INTENTS: tuple[str, ...] = ("Explore", "Current", "Retired", "Reference", "Learn")


def _categories(json_output: bool) -> list[str]:
    try:
        return load_core_config(cli.get_core_config_path()).taxonomy.categories
    except CoreConfigError as exc:
        fail(str(exc), code=CODE_INVALID_INPUT, json_output=json_output)


def _cast_intent(value: str) -> Intent:
    """Narrow an already-validated `--intent` string for mypy."""
    return value  # type: ignore[return-value]


@remote_app.command("bootstrap")
def bootstrap_cmd(
    intent: str = typer.Option(
        "", "--intent", help="Intent for the created Lists. Required."
    ),
    yes: bool = typer.Option(False, "--yes", help="Required: this writes to GitHub."),
    force: bool = typer.Option(
        False, "--force", help="Create even while List names need attention."
    ),
    private: bool = typer.Option(False, "--private", help="Create private Lists."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Create one List per blessed Category that has none, under `--intent`.

    Creates the whole missing set in one call, which is why it is named
    for seeding a taxonomy rather than for creating a List.

    Refuses without `--intent`: ghstars never guesses one (ticket 03). A
    malformed or unblessed List name blocks the run, because a rename can
    turn an unblessed Category into a blessed one and remove the need to
    create anything; `--force` proceeds anyway.

    Never renames and never deletes. `ghstars doctor` reports what this
    would create.
    """
    categories = _categories(json_output)
    if not yes:
        fail(
            "--yes is required. This creates Lists on GitHub.",
            code=CODE_INVALID_INPUT,
            json_output=json_output,
        )
    if intent not in _INTENTS:
        fail(
            f"--intent is required, one of {', '.join(_INTENTS)}. "
            "ghstars never guesses an Intent.",
            code=CODE_INVALID_INPUT,
            json_output=json_output,
        )

    try:
        report = diagnose(cli.get_client().fetch_lists(), categories=categories)
        if report.create_blocked and not force:
            fail(
                f"{report.blocked_reason}. Fix the names, or pass --force.",
                code=CODE_INVALID_INPUT,
                json_output=json_output,
            )
        planned = planned_creates(report, intent=_cast_intent(intent))
        created = bootstrap_lists(
            cli.get_client(),
            report,
            intent=_cast_intent(intent),
            is_private=private,
        )
    except GitHubApiError as exc:
        fail(str(exc), code=CODE_NETWORK_FAILURE, json_output=json_output)

    if json_output:
        typer.echo(json.dumps({"created": created, "planned": planned}))
        return
    if not created:
        typer.echo("Nothing to create: every blessed Category already has a List.")
        return
    typer.echo(f"Created {len(created)} List(s):")
    for name in created:
        typer.echo(f"  + {name}")
    typer.echo("Run `ghstars sync` to refresh local state.")


@remote_app.command("rename-list")
def rename_list_cmd(
    old_name: str = typer.Argument(..., help="Current List name, exactly as on GitHub."),
    new_name: str = typer.Argument(..., help="New List name, e.g. 'Learn: General'."),
    yes: bool = typer.Option(False, "--yes", help="Required: this writes to GitHub."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Rename exactly one List, including across Intents.

    `category rename` renames every Intent-variant of one Category at
    once and cannot change an Intent. This renames a single List to any
    valid name, which is what a malformed name needs.

    Refuses a malformed or unblessed target name, with no override.
    Local state is stale afterwards -- run `ghstars sync`.
    """
    categories = _categories(json_output)
    if not yes:
        fail(
            "--yes is required. This renames a List on GitHub.",
            code=CODE_INVALID_INPUT,
            json_output=json_output,
        )

    try:
        renamed = rename_list(
            cli.get_client(), old_name, new_name, categories=categories
        )
    except (ListNotFoundError, ListNameTakenError, UnwritableListNameError) as exc:
        fail(str(exc), code=CODE_INVALID_INPUT, json_output=json_output, target=old_name)
    except GitHubApiError as exc:
        fail(str(exc), code=CODE_NETWORK_FAILURE, json_output=json_output)

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "id": renamed.id,
                    "old_name": old_name,
                    "name": renamed.name,
                    "intent": renamed.intent,
                    "category": renamed.category,
                }
            )
        )
        return
    typer.echo(f"Renamed {old_name!r} to {renamed.name!r}.")
    typer.echo("Run `ghstars sync` to refresh local state.")


__all__ = ["bootstrap_cmd", "rename_list_cmd"]
