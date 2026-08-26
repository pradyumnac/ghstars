# 0006 — The TUI can sync on an explicit keypress

## Status

accepted

## Implemented

not-started

## Context

Supersedes ADR 0003. ADR 0003 established the rule this decision keeps: no
surface may pull Star or List data on its own initiative. That rule stands.

ADR 0003 also wrote down the list of allowed triggers for a live fetch:
`ghstars sync`, `ghstars category rename`, `ghstars category drain`, and the
TUI's rate-limit refresh key. A TUI sync key was not on that list.
`src/ghstars/tui/app.py` states the same rule more strictly than ADR 0003
does: "This module never calls `ghstars.core.sync`."

That strict reading creates a real problem. The TUI is the surface where the
user notices the data is stale, because the TUI is where the user reads it.
Under ADR 0003 the user must quit the TUI, run `ghstars sync`, and start the
TUI again. The user rejected this during the TUI design session (2026-08-18)
and stated the rule directly: pressing a sync key *is* the intent to sync,
and a TUI that can only ever show stale data has no purpose.

Two facts shape the decision:

- A full sync against the user's real account (1530 Stars, 7 Lists) takes
  minutes. It is not an operation that can hide inside a keypress handler.
- `ghstars.core.sync.sync()` now takes an `on_stage` callback. A caller can
  report each phase without changing what `sync()` does.

## Decision

The TUI can run a full sync, and only when the user presses the sync key.

- The sync key is separate from the rate-limit refresh key. One key means
  "run a full sync"; the other means "re-check the API rate limit alone".
  Two different costs must never share one key.
- The TUI reports sync progress through `sync()`'s `on_stage` callback, in a
  modal the user can see.
- Every other rule in ADR 0003 stands unchanged. No surface auto-syncs on
  startup, on a timer, or as a side effect of an unrelated action.
- `check_rate_limit()` stays the read-only metadata exception ADR 0003 made
  it.

## Consequences

- `src/ghstars/tui/app.py`'s module docstring is now wrong and must change.
  The claim "this module never calls `ghstars.core.sync`" no longer holds.
- The TUI gains a long-running operation. It must decide what happens to a
  selection and to staged `pending_list_ids` while a sync runs, and it must
  stop a second sync from starting while one is in flight.
- The rule is now "explicit user action", and no longer "explicit user action
  from a fixed list of commands". A future surface can add its own sync
  trigger without a new ADR, as long as a user action starts it.
- `ghstars.core.sync` gains a second production caller. Its `on_stage`
  callback is now load-bearing for the TUI, not only for the CLI spinner.

## Alternatives considered

- **Keep ADR 0003 unchanged; the TUI shows a "last synced" time and tells the
  user to quit and run `ghstars sync`** — rejected by the user. It keeps the
  ADR tidy and makes the tool worse at its main job.
- **Sync automatically when the TUI opens, or when data looks old** —
  rejected. This is the exact behaviour ADR 0003 exists to prevent. It makes
  API cost invisible and unpredictable.
- **Edit ADR 0003 in place to add the TUI sync key** — rejected. An accepted
  decision changes by supersession only, so the earlier reasoning stays
  readable.
