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
from ghstars.core.doctor import DoctorReport, diagnose
from ghstars.github import GitHubApiError


@app.command("doctor")
def doctor_cmd(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Report how the GitHub account measures up against the taxonomy.

    Read-only, always: every repair lives in its own command, one per
    kind of problem (`ghstars remote bootstrap`, `ghstars remote
    rename-list`, `ghstars untag`). Reads live Lists, so it diagnoses the
    account rather than the last sync, and never prompts (ticket 30
    Scope 0) -- the skill layer walks the report and calls the repairs.

    A problem with one possible repair is reported as the command to
    run. A problem with two valid repairs is reported in prose, because
    ghstars must not choose between them (ticket 03).
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

    if json_output:
        typer.echo(json.dumps(report.model_dump(mode="json")))
    else:
        _render(report)

    if not report.ok:
        raise typer.Exit(code=EXIT_TERMINAL)


def _render(report: DoctorReport) -> None:
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
        typer.echo(
            "Stars in the triage inbox and a classified List: "
            f"{len(report.star_problems)}"
        )
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
        typer.echo("  fix: ghstars remote bootstrap --yes --intent <Intent>")

    if report.create_blocked:
        typer.echo(f"Bootstrap blocked: {report.blocked_reason}")

    if report.ok:
        typer.echo("Doctor: ok")


__all__ = ["doctor_cmd"]
