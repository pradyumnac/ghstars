# 0010 — CLI JSON and exit-code error contract

## Status

proposed

## Implemented

n/a

## Context

Ticket 30 turns the CLI into a stable interface for an agentic LLM caller.
Scope 0's first review (ticket 30) found the error path unusable for that
caller: under `--json`, every failure still printed prose to standard
error, and one exit code (1) covered every kind of failure — "no local
record", "rate limit exceeded", "state lock held", "List-membership
drift", and "network failure" were indistinguishable. An agent in a retry
loop cannot decide whether retrying is worth it, and a script parsing
`--json` output cannot branch on *why* a call failed without scraping an
English sentence.

Ticket 30 Decision 23 stops this ADR at `proposed`: implement the contract
exactly as it is written here, but do not accept it until Scope 0's second
review (against the live account, ticket 30) confirms it holds up in
practice.

## Decision

Every CLI command that can fail routes the failure through one function,
`ghstars.cli.errors.fail()`.

Under `--json`, a failure writes one JSON object to standard error:

```json
{"error": {"code": "no_local_record", "message": "...", "target": "a/b"}}
```

`target` is present only when the failure names a specific thing (a repo,
a Category, a set of field names); a failure with no natural target (e.g.
a rate limit) omits it. Without `--json`, the same failure prints
`error: <message>` to standard error instead — the message text is not
part of the machine contract in either mode; only `code` is.

The exit code is one of three flat values, chosen by `code` alone,
whether or not the caller passed `--json`:

| Exit code | Meaning |
| --- | --- |
| 1 (`EXIT_TERMINAL`) | The failure will not resolve by retrying the same call. |
| 3 (`EXIT_RETRYABLE`) | The failure might resolve on retry. |
| 4 (`EXIT_PARTIAL`) | A bulk call (ticket 30 Scope 4) succeeded for some explicit targets and failed for others. |

Typer's own exit code 2 stays reserved for a usage error (bad arguments,
missing required option); ghstars never raises it itself, and no command
maps a `code` onto it.

Machine codes, and which exit code each maps to:

| Code | Exit code | Raised when |
| --- | --- | --- |
| `no_local_record` | 1 | No local record exists for the named repo or Category. |
| `star_archived` | 1 | The target Star is Archived (unstarred) locally. |
| `list_membership_drift` | 1 | Local List membership has diverged from GitHub's since the last sync. |
| `tag_push_failed` | 1 | Pushing a tag mutation to GitHub failed. |
| `invalid_input` | 1 | A malformed argument, config file, or Category name. |
| `unknown_field` | 1 | `--fields` named a field the record type doesn't have. |
| `tool_unavailable` | 1 | A required external tool (`git`) could not be run at all. |
| `rate_limit_exceeded` | 3 | GitHub's API rate limit was hit. |
| `state_lock_held` | 3 | The local state file lock is held by another `ghstars` process. |
| `network_failure` | 3 | A GitHub API call failed for a reason other than the rate limit. |

This list is the floor, not the ceiling: a later ticket may add a code,
but it must fall into one of the two buckets above, and an existing code's
exit-code mapping never changes once accepted.

There is no schema version on either the error envelope or any other
`--json` output (ticket 30 Decision 9/18). A shape change is a hard break,
landed together with whatever ticket 14 agent-skill change it demands.

## Consequences

- Every command's `except` block names a `code` explicitly instead of
  reusing one generic failure path — a larger diff than a single shared
  "print and exit 1" helper, but the only way an agent can branch on
  *why* a call failed without parsing prose.
- Adding a new failure mode means picking one of the two exit-code
  buckets, not inventing a new exit code — keeps the contract at three
  flat values indefinitely.
- A caller that only checks the exit code (not `--json`) already gets the
  retryable/terminal split; `--json` adds *which* failure, not *whether*
  to retry.
- Because there is no schema version, a future field-set or error-code
  change ships as a breaking change with no deprecation window — callers
  (starting with ticket 14's agent skill) must track ghstars' own
  releases, not a version field in the payload.

## Alternatives considered

- **HTTP-style numeric status codes** (400/429/503/...) instead of named
  string codes — rejected: a numeric code invites confusion with the
  process exit code sitting right next to it in the same JSON object, and
  a named string is more legible in a log line without a lookup table.
- **One exit code per failure kind** (a wider reserved range) — rejected
  by ticket 30 Decision 15: three flat codes are enough for an agent to
  decide retry-or-not, and the JSON `code` field already carries the
  detail a wider exit-code range would exist to convey.
- **A reserved partial-failure code per bulk command** instead of one
  shared `EXIT_PARTIAL` — rejected: every bulk command reports the same
  per-target success/failure array shape (ticket 30 Scope 4), so one
  shared code follows the same "identical shape everywhere" rule as the
  list-envelope contract (ticket 30 Decision 19).

## Changelog

None.
