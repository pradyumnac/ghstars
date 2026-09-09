import json

import typer

from ghstars import cli
from ghstars.cli import app  # imported by name for mypy; see commands/sync.py
from ghstars.cli.errors import (
    CODE_INVALID_INPUT,
    CODE_NETWORK_FAILURE,
    EXIT_TERMINAL,
    fail,
)
from ghstars.core import CoreConfigError, load_core_config
from ghstars.core.doctor import DoctorReport, bootstrap_lists, diagnose
from ghstars.core.models import Intent
from ghstars.github import GitHubApiError

_INTENTS: tuple[str, ...] = ("Explore", "Current", "Retired", "Reference", "Learn")


@app.command("doctor")
def doctor_cmd(
    fix: bool = typer.Option(False, "--fix", help="Create missing Lists on GitHub."),
    yes: bool = typer.Option(False, "--yes", help="Required by --fix."),
    intent: str = typer.Option(
        "", "--intent", help="Intent for created Lists. Required by --fix."
    ),
    force: bool = typer.Option(
        False, "--force", help="Create even while List names need attention."
    ),
    private: bool = typer.Option(False, "--private", help="Create private Lists."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Check the GitHub account against the taxonomy and report a repair plan.

    Reads live Lists, never local state, so it diagnoses the account rather
    than the last sync. Never prompts (ticket 30 Scope 0) -- the skill layer
    walks the plan interactively and calls back with explicit flags.

    A malformed or unblessed name blocks `--fix`, because a rename can turn
    an unblessed Category into a blessed one and remove the need to create
    anything. `--force` proceeds anyway.
    """
    try:
        categories = load_core_config(cli.get_core_config_path()).taxonomy.categories
    except CoreConfigError as exc:
        fail(str(exc), code=CODE_INVALID_INPUT, json_output=json_output)

    try:
        lists = cli.get_client().fetch_lists()
    except GitHubApiError as exc:
        fail(str(exc), code=CODE_NETWORK_FAILURE, json_output=json_output)

    report = diagnose(lists, categories=categories)

    created: list[str] = []
    if fix:
        if not yes:
            fail(
                "--fix requires --yes. It creates Lists on GitHub.",
                code=CODE_INVALID_INPUT,
                json_output=json_output,
            )
        if intent not in _INTENTS:
            fail(
                f"--fix requires --intent, one of {', '.join(_INTENTS)}. "
                "ghstars never guesses an Intent.",
                code=CODE_INVALID_INPUT,
                json_output=json_output,
            )
        if report.create_blocked and not force:
            fail(
                f"{report.blocked_reason}. Fix the names, or pass --force.",
                code=CODE_INVALID_INPUT,
                json_output=json_output,
            )
        try:
            created = bootstrap_lists(
                cli.get_client(),
                report,
                intent=cast_intent(intent),
                is_private=private,
            )
        except GitHubApiError as exc:
            fail(str(exc), code=CODE_NETWORK_FAILURE, json_output=json_output)

    if json_output:
        typer.echo(
            json.dumps({**report.model_dump(mode="json"), "created": created})
        )
    else:
        _render(report, created, intent)

    if not report.ok and not created:
        raise typer.Exit(code=EXIT_TERMINAL)


def cast_intent(value: str) -> Intent:
    """Narrow an already-validated `--intent` string for mypy."""
    return value  # type: ignore[return-value]


def _render(report: DoctorReport, created: list[str], intent: str) -> None:
    typer.echo(f"Lists checked: {report.list_count}")

    if report.problems:
        typer.echo(f"Names needing attention: {len(report.problems)}")
        for problem in report.problems:
            typer.echo(f"  - {problem.list_name}: {problem.detail}")
            for repair in problem.repairs:
                typer.echo(f"      fix: {repair}")
    else:
        typer.echo("Names: ok")

    if report.star_problems:
        typer.echo(f"Stars in the triage inbox and a classified List: {len(report.star_problems)}")
        for star_problem in report.star_problems:
            typer.echo(
                f"  - {star_problem.full_name}: in {star_problem.in_triage_inbox} "
                f"and {star_problem.classified}"
            )
            for repair in star_problem.repairs:
                typer.echo(f"      fix: {repair}")

    if report.missing_categories:
        typer.echo(f"Blessed Categories with no List: {len(report.missing_categories)}")
        for category in report.missing_categories:
            typer.echo(f"  - {category}")
        if not created:
            hint = intent or "Explore"
            typer.echo(f"  run: ghstars doctor --fix --yes --intent {hint}")

    if created:
        typer.echo(f"Created {len(created)} List(s):")
        for name in created:
            typer.echo(f"  + {name}")
    elif report.create_blocked:
        typer.echo(f"Create blocked: {report.blocked_reason}")

    if report.ok:
        typer.echo("Doctor: ok")


__all__ = ["doctor_cmd"]
