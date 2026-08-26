# 09 — TUI: interactive tagging, bulk tagging, retagging

**What to build:** A Textual TUI, a thin wrapper over `ghstars.core`, for fast interactive triage: tag a single Star, bulk-tag a batch, and retag (move a Star between Categories or Intents as usage evolves) without leaving the terminal. Each List's public/private status is shown explicitly, so a private List is never mistaken for a public one. Also shows the remaining GitHub API rate limit (spec story 49, added after ticket 04 shipped — a full sync costs real API points, non-incremental, see docs/explanation/known-limitations.md), so the user can see when they're approaching a sync-blocking limit before it happens.

**Blocked by:** 04.

**Status:** done

- [x] TUI supports single-item tagging against `ghstars.core`
- [x] TUI supports bulk tagging across a selected batch of Stars
- [x] TUI supports retagging (moving a Star between Category/Intent)
- [x] Each List's public/private status is visibly and unambiguously displayed
- [x] TUI shows the remaining GitHub API rate limit
  (`GitHubClient.check_rate_limit()`). This is a UI-only addition.

## Comments

Commit `8c55b2d` added `ghstars tui`. The TUI calls `tag_star()` for
single-item tags, multi-selection bulk tags, and retags. Star rows, the List
picker, and the Lists overview show each List's visibility. `RateLimitBar`
loads on startup and refreshes on demand. Ticket-specific tests pass.
