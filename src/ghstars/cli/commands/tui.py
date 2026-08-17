from ghstars import cli
from ghstars.cli import app  # imported by name for mypy; see commands/sync.py


@app.command("tui")
def tui_cmd() -> None:
    """Launch the interactive TUI for tagging, bulk-tagging, and retagging.

    Imports `ghstars.tui` lazily so every other subcommand keeps starting
    up without paying for Textual's import cost.
    """
    from ghstars.tui import TuiApp

    TuiApp(client=cli.get_client(), store=cli.get_store()).run()
