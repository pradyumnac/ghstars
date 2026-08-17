"""Thin wrapper around the user's own git history for `state/` (ticket 11).

ghstars never runs `git init` on `state/` and never commits to it (ADR
0002, `StateStore`'s docstring): tracking that directory in git is entirely
the user's own choice, e.g. as part of a dotfiles repo. This module only
shells out to read-only `git` commands (`rev-parse`, `diff`, `log`) against
whatever repo the user already set up -- no bespoke diff engine, and no
mutation of the user's git history.
"""

import subprocess
from pathlib import Path


class GitUnavailableError(Exception):
    """The `git` binary itself couldn't be run (missing, not executable, ...).

    Distinct from git running successfully but reporting "not a repo" --
    that's a normal `returncode != 0`, not this.
    """


def _run(state_dir: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run `git -C state_dir <args>`, raising `GitUnavailableError` if the
    `git` binary itself can't be executed at all.
    """
    try:
        return subprocess.run(
            ["git", "-C", str(state_dir), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise GitUnavailableError("git is not installed") from exc
    except OSError as exc:
        raise GitUnavailableError(f"git is not usable ({exc})") from exc


def git_unavailable_reason(state_dir: Path) -> str | None:
    """None if `state_dir` sits inside a git work tree; otherwise why not.

    Uses `git rev-parse --is-inside-work-tree` so this also recognizes a
    repo rooted above `state_dir` (e.g. the user tracking all of
    `~/.ghstars/` from one repo), not just a `.git` directly inside it.
    """
    try:
        result = _run(state_dir, ["rev-parse", "--is-inside-work-tree"])
    except GitUnavailableError as exc:
        return str(exc)
    if result.returncode != 0 or result.stdout.strip() != "true":
        return f"{state_dir} is not git-tracked"
    return None


def run_git_diff(
    state_dir: Path, *, log: bool, extra_args: list[str]
) -> subprocess.CompletedProcess[str]:
    """Run `git diff` (or `git log -p` with `log=True`) against `state_dir`.

    Read-only: only ever `diff`/`log`, plus caller-supplied `extra_args`
    (revisions, paths, `--stat`, etc.) passed straight through to git.

    The repo backing `state_dir` may be rooted above it (a user tracking
    all of `~/.ghstars/` from one repo, per `git_unavailable_reason`'s
    docstring) -- without a pathspec, `git diff`/`git log` would then show
    changes across the *whole* repo, not just `state/`. So unless the
    caller already supplied their own pathspec (an explicit `--`), this
    scopes the command to `state_dir` itself via `-- .` (resolved relative
    to `-C state_dir`).
    """
    git_args = ["log", "-p"] if log else ["diff"]
    git_args += extra_args
    if "--" not in extra_args:
        git_args += ["--", "."]
    return _run(state_dir, git_args)
