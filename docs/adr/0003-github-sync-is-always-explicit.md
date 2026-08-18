# 0003 — GitHub sync is always explicit, never auto-triggered

## Status

superseded by 0004

## Implemented

not-started

## Context

ghstars keeps a local snapshot of Stars and Lists under `~/.ghstars/state/`
(ADR 0002) and treats GitHub as the sole source of truth for List membership
(ADR 0001). As more surfaces land on top of that state — the CLI (tickets
01-11), a Textual TUI (ticket 09), and a planned agent skill (ticket 14) —
each one is a new place that could, deliberately or accidentally, decide to
call out to the live GitHub API on its own initiative (e.g. "refresh on
every screen open," "auto-sync before every mutating command").

The user set an explicit constraint mid-session, during the 07/09/10/11
parallel-ticket layer: every surface must always serve from local state by
default, and a real GitHub API fetch must only happen when the user takes an
explicit action — never as a side effect of opening a screen, running an
unrelated command, or an agent skill invocation.

A whole-project advisor review (2026-08-17) audited every reachable call
site of `sync()`, `client.fetch_stars()`, `client.fetch_lists()`, and every
mutating `GitHubClient` method across the codebase as it stood after the
07/09/10/11 merge, to check the code already matched this rule. It found one
borderline case — `ghstars tui`'s `on_mount` unconditionally calls
`GitHubClient.check_rate_limit()`, a real API call, the instant the TUI
launches — and the user confirmed that one is an acceptable exception (see
Decision).

## Decision

A real GitHub API fetch of Star or List data happens only via an explicit
user action: `ghstars sync`, `ghstars category rename`/`ghstars category
drain` (which deliberately fetch fresh Star/List state immediately before
writing a bulk change, per ticket 17's skip-diverged-items design
constraint — a narrow, invocation-scoped exception, not a background
refresh), or an explicit manual action like the TUI's `r` rate-limit-refresh
key. No surface — CLI, TUI, or the future agent skill (ticket 14) — may
auto-pull or auto-sync Star/List data on its own initiative (on startup, on
an unrelated command, on a timer, etc.). Everything else always serves from
local state (`~/.ghstars/state/`).

**Exception**: read-only account metadata that is not Star/List data —
currently only `GitHubClient.check_rate_limit()` — may be fetched
automatically (e.g. shown on `ghstars tui` launch) without counting as a
"sync." It pulls no Star/List data and writes nothing to `state/`, so it
carries none of the two-places-of-truth risk this decision exists to guard
against.

## Consequences

- Every future ticket that adds a new surface (ticket 13 packaging, ticket
  14's agent skill) must route any live GitHub read/write through an
  explicit user action, not a convenience auto-refresh.
- `ghstars category rename`/`drain`'s fresh-fetch-before-write stays a
  documented, narrow exception tied to one specific bulk-write safety
  concern — it must not be generalized into a broader "fetch fresh state
  whenever convenient" pattern without a new decision here.
- If a future feature needs live account metadata beyond the rate limit
  (e.g. auth/scope status), the same read-only-metadata exception can cover
  it, but anything that returns Star or List data does not qualify and needs
  an explicit trigger.
- `GitHubClient`'s single `_graphql()` chokepoint (noted by the same
  advisor review) is a natural place to eventually add a mechanical check —
  e.g. a test asserting zero live calls happen from a bare `ghstars tui`
  launch other than `check_rate_limit()` — rather than relying on manual
  review each time a new layer merges.

## Alternatives considered

- **Auto-sync on TUI/CLI startup for a fresher-feels-better UX** — rejected;
  makes GitHub API cost and rate-limit exposure unpredictable and invisible
  to the user, and contradicts the local-state-first design already
  established by ADR 0002.
- **Treat `check_rate_limit()` the same as any other live call and forbid
  it too** — rejected by the user; it carries none of the risk a Star/List
  fetch does (no data pulled, nothing written), and ticket 09 explicitly
  speced showing it on TUI launch as a safety signal (so the user can see
  they're approaching a sync-blocking limit before it happens).
