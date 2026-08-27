import typer

from ghstars import cli
from ghstars.cli import app  # imported by name for mypy; see commands/sync.py
from ghstars.cli.errors import CODE_INVALID_INPUT, CODE_TOOL_UNAVAILABLE, fail
from ghstars.cli.git_diff import GitUnavailableError, run_git_diff

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
        "diff.",
    ),
    patch: bool = typer.Option(
        False,
        "--patch",
        help="Show the full working-tree patch (`git diff`) instead of the "
        "default summary (`git diff --stat`).",
    ),
) -> None:
    """Wrap `git diff`/`git log -p` against `state/`'s own git repo.

    ghstars never runs `git init` on `state/` and never commits to it (ADR
    0002) -- this only works if the user has git-tracked `state/`
    themselves, e.g. as part of a dotfiles repo. No bespoke diff engine:
    this shells out to the user's own `git` and shows its output verbatim.

    The bare command (no `--log`, no `--patch`) prints a summary
    (`git diff --stat`), not the full patch -- this is the agent contract
    (ticket 30): call it with no arguments and detect a change by non-empty
    output. `--patch` gets the full patch for a human reading it. The exit
    code is always git's own, verbatim -- `git diff`/`git diff --stat`
    exit 0 whether or not there are changes, so the exit code never says
    whether anything changed; only the output does.
    """
    state_dir = cli.get_store().base_dir
    reason = cli.git_unavailable_reason(state_dir)
    if reason is not None:
        fail(
            f"no git history available for {state_dir} ({reason}). ghstars "
            "never runs `git init` or commits state/ on its own -- track it "
            "yourself (`git init` and commit inside that directory) if you "
            "want `ghstars diff`.",
            code=CODE_INVALID_INPUT,
            json_output=False,
        )

    try:
        result = run_git_diff(state_dir, log=log, patch=patch, extra_args=args or [])
    except GitUnavailableError as exc:
        fail(
            f"{exc} while running `git diff`/`git log -p`.",
            code=CODE_TOOL_UNAVAILABLE,
            json_output=False,
        )

    if result.stdout:
        typer.echo(result.stdout, nl=False)
    if result.returncode != 0:
        if result.stderr:
            typer.echo(result.stderr, err=True, nl=False)
        raise typer.Exit(code=result.returncode)
