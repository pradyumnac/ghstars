from typing import NoReturn

import typer


def fail(message: str) -> NoReturn:
    """Hard-fail with a clear error — never a prompt, never a hang.

    Every command uses this for a missing or invalid required decision,
    under --json or not (spec stories 28-30).
    """
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)
