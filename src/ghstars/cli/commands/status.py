import json

import typer

from ghstars import cli
from ghstars.cli import app  # imported by name for mypy; see commands/sync.py
from ghstars.core.status import build_status


@app.command("status")
def status_cmd(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Report local-state health in one call: last sync time, Retriage
    Queue count, unclassified (`Explore: General`) count, and a
    deterministic offline verify pass/fail (ticket 08).

    Reads only `StateStore.load_*()` -- never a live `GitHubClient` call
    -- so an agent can call this before deciding whether a `sync` is
    even worth the round trip.
    """
    report = build_status(cli.get_store())

    if json_output:
        typer.echo(json.dumps(report.model_dump(mode="json")))
        return

    last_sync = report.last_sync_at.isoformat() if report.last_sync_at else "never"
    typer.echo(f"Last sync: {last_sync}")
    typer.echo(f"Retriage Queue: {report.retriage_queue_count}")
    typer.echo(f"Unclassified (Explore: General): {report.unclassified_count}")
    if report.verify_ok:
        typer.echo("Verify: ok")
    else:
        typer.echo(f"Verify: FAILED ({len(report.verify_problems)} problem(s))")
        for problem in report.verify_problems:
            typer.echo(f"  - {problem}")
