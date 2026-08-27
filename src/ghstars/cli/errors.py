"""Machine-readable CLI error contract (ticket 30).

Every hard failure goes through `fail()`. Under `--json`, it writes a JSON
error object (`{"error": {"code", "message", "target"?}}`) to standard
error instead of prose. Every failure, `--json` or not, exits with one of
three flat codes: `EXIT_TERMINAL` (1) for a failure that will not resolve
on retry, `EXIT_RETRYABLE` (3) for one that might, and `EXIT_PARTIAL` (4)
for a bulk call that succeeded for some targets and failed for others
(ticket 30 Scope 4). Typer's own exit code 2 stays reserved for a usage
error (bad arguments); ghstars never raises it itself.

This is the CLI JSON/exit-code contract ADR 0010
(`docs/adr/0010-cli-json-and-exit-code-contract.md`) describes. The ADR
stays `proposed` (ticket 30 Decision 23); implement the contract exactly
as it proposes it, here and at every call site.

Machine codes are named module constants so every command imports the
same string instead of re-typing it. `RETRYABLE_CODES` names which of
them get `EXIT_RETRYABLE`; every other code is terminal.
"""

from __future__ import annotations

import json
from typing import NoReturn

import typer

EXIT_TERMINAL = 1
EXIT_RETRYABLE = 3
EXIT_PARTIAL = 4

CODE_NO_LOCAL_RECORD = "no_local_record"
CODE_STAR_ARCHIVED = "star_archived"
CODE_LIST_MEMBERSHIP_DRIFT = "list_membership_drift"
CODE_TAG_PUSH_FAILED = "tag_push_failed"
CODE_RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
CODE_STATE_LOCK_HELD = "state_lock_held"
CODE_NETWORK_FAILURE = "network_failure"
CODE_INVALID_INPUT = "invalid_input"
CODE_UNKNOWN_FIELD = "unknown_field"
CODE_TOOL_UNAVAILABLE = "tool_unavailable"

RETRYABLE_CODES = frozenset(
    {CODE_RATE_LIMIT_EXCEEDED, CODE_STATE_LOCK_HELD, CODE_NETWORK_FAILURE}
)


def fail(
    message: str,
    *,
    code: str,
    json_output: bool,
    target: str | None = None,
) -> NoReturn:
    """Hard-fail with a clear error — never a prompt, never a hang.

    Every command uses this for a missing or invalid required decision,
    under `--json` or not. Under `--json`, `code`/`message`/`target` form
    a JSON error object on standard error instead of prose. The exit code
    is `EXIT_RETRYABLE` when `code` is in `RETRYABLE_CODES`, otherwise
    `EXIT_TERMINAL` — this applies whether or not the caller passed
    `--json`, so a script parsing exit codes alone still gets the
    retryable/terminal split.
    """
    if json_output:
        error: dict[str, str] = {"code": code, "message": message}
        if target is not None:
            error["target"] = target
        typer.echo(json.dumps({"error": error}), err=True)
    else:
        typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=EXIT_RETRYABLE if code in RETRYABLE_CODES else EXIT_TERMINAL)
