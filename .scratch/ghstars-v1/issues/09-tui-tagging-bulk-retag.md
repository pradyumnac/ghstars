# 09 — TUI: interactive tagging, bulk tagging, retagging

**What to build:** A Textual TUI, a thin wrapper over `ghstars.core`, for fast interactive triage: tag a single Star, bulk-tag a batch, and retag (move a Star between Categories or Intents as usage evolves) without leaving the terminal. Each List's public/private status is shown explicitly, so a private List is never mistaken for a public one. Also shows the remaining GitHub API rate limit (spec story 49, added after ticket 04 shipped — a full sync costs real API points, non-incremental, see docs/explanation/known-limitations.md), so the user can see when they're approaching a sync-blocking limit before it happens.

**Blocked by:** 04.

**Status:** ready-for-agent

- [ ] TUI supports single-item tagging against `ghstars.core`
- [ ] TUI supports bulk tagging across a selected batch of Stars
- [ ] TUI supports retagging (moving a Star between Category/Intent)
- [ ] Each List's public/private status is visibly and unambiguously displayed
- [ ] TUI shows remaining GitHub API rate limit (`GitHubClient.check_rate_limit()`, already implemented since ticket 01/02 — this is a UI-only addition, no new core/client work needed)
